"""Activities router (P5 B8): teacher builder CRUD + gated publish.

Two routers are exported (mirror the ``checkpoints.py`` course/item split):

- ``course_router`` under ``/courses/{course_id}`` — create + list, guarded by
  ``get_owned_course`` (a student → 403 via ``require_instructor``; a non-owner
  instructor → 404 so course existence never leaks).
- ``router`` under ``/activities`` — get / patch / delete / publish, guarded by a
  per-activity ownership helper ``_owned_activity`` mirroring ``_owned_checkpoint``
  (404 on non-owner, never 403).

``config`` is shape-validated per ``format`` (swipe → ``prompts``, vote →
``options``, comment_reaction → ``reactions``); a malformed config raises the
typed ``ACTIVITY_CONFIG_INVALID`` (422). Publish runs the activity status
transition and — for a SCORE-BEARING activity only — the shared
``assert_score_policy_complete`` gate (422 ``SCORE_POLICY_INCOMPLETE``) BEFORE
flipping state; then it writes an ``activity`` work_item transactionally +
idempotently (mirror B5 ``publish_quiz`` / ``publish_checkpoint``). A
participation-only activity publishes WITHOUT the gate.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import (
    get_current_user,
    get_db,
    get_owned_course,
    require_instructor,
)
from app.database import async_session_factory
from app.models.activity import Activity, ActivityResponse
from app.models.course import Course
from app.models.curriculum import CourseMeeting
from app.models.score import ScoreCategory
from app.models.user import User
from app.schemas.activity import (
    ActivityCreate,
    ActivityIntro,
    ActivityRead,
    ActivityResponseResult,
    ActivityResponseSubmit,
    ActivityResults,
    ActivityUpdate,
)
from app.schemas.common import APIResponse
from app.services.activity_monitor import (
    compute_activity_monitor_state,
    monitor_manager,
)
from app.services.activity_responses import (
    OPEN_STATUSES,
    submit_activity_response,
)
from app.services.auth import verify_jwt
from app.services.score_policy import assert_score_policy_complete
from app.services.work_items import upsert_work_item

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activities", tags=["activities"])
course_router = APIRouter(prefix="/courses/{course_id}", tags=["activities"])

# The renderable-payload key each format's ``config`` must carry (§4.4). A swipe
# needs a prompt list, a vote needs an option list, a comment_reaction needs a
# reaction set. The value must be a NON-EMPTY list.
_CONFIG_KEY_BY_FORMAT: dict[str, str] = {
    "swipe": "prompts",
    "vote": "options",
    "comment_reaction": "reactions",
}

# Activity status machine (Decision 3): the activity CHECK enum is the checkpoint
# machine MINUS the intermediate teacher_editing/approved/scheduled states, so a
# publish is a DIRECT ``draft→published`` edge. Reusing ``checkpoints.py::
# assert_transition`` would forbid that edge (its map has no draft→published), so
# activities carry their own small guard here.
_ACTIVITY_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"published"}),
    "published": frozenset({"live", "closed"}),
    "live": frozenset({"closed"}),
    "closed": frozenset({"archived"}),
    "archived": frozenset(),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _config_invalid(fmt: str, key: str) -> HTTPException:
    """A typed ``ACTIVITY_CONFIG_INVALID`` refusal (§3.4), HTTP 422."""
    return HTTPException(
        status_code=422,
        detail={
            "code": "ACTIVITY_CONFIG_INVALID",
            "message": (
                f"A '{fmt}' activity requires a non-empty '{key}' list in its "
                "config."
            ),
            "missing": [key],
        },
    )


def validate_activity_config(
    fmt: str, config: dict | None, *, required: bool
) -> None:
    """Shape-validate an activity ``config`` for its ``format``.

    - ``required=False`` (create / patch): a ``None`` config is allowed (the
      teacher may fill it later) but a PRESENT config must carry the format's
      non-empty renderable list, else ``ACTIVITY_CONFIG_INVALID``.
    - ``required=True`` (publish): a ``None`` / malformed config is rejected — a
      publishable activity must carry its renderable payload.
    """
    key = _CONFIG_KEY_BY_FORMAT.get(fmt)
    if key is None:  # defensive — the schema Literal already constrains format.
        raise _config_invalid(fmt, "config")
    if config is None:
        if required:
            raise _config_invalid(fmt, key)
        return
    if not isinstance(config, dict):
        raise _config_invalid(fmt, key)
    value = config.get(key)
    if not isinstance(value, list) or not value:
        raise _config_invalid(fmt, key)


async def _validate_activity_refs(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
    meeting_id: uuid.UUID | None,
    score_category_id: uuid.UUID | None,
) -> None:
    """Refuse a ``meeting_id`` / ``score_category_id`` that isn't in THIS course.

    A teacher owns the course (``get_owned_course`` / ``_owned_activity``), but a
    supplied foreign ``meeting_id`` / ``score_category_id`` from ANOTHER course
    would be persisted unchecked → cross-course misattribution in
    ``build_score_records``. Mirrors ``documents.py::assign_document``'s
    ``MEETING_NOT_FOUND`` refusal (404 either way, so cross-course existence never
    leaks). A ``None`` value (unset / explicit unassign) is always allowed.
    """
    if meeting_id is not None:
        meeting = (
            await db.execute(
                select(CourseMeeting.id).where(
                    CourseMeeting.id == meeting_id,
                    CourseMeeting.course_id == course_id,
                    CourseMeeting.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "MEETING_NOT_FOUND",
                    "message": "Meeting not found in this course",
                },
            )
    if score_category_id is not None:
        category = (
            await db.execute(
                select(ScoreCategory.id).where(
                    ScoreCategory.id == score_category_id,
                    ScoreCategory.course_id == course_id,
                    ScoreCategory.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "SCORE_CATEGORY_NOT_FOUND",
                    "message": "Score category not found in this course",
                },
            )


async def _owned_activity(
    activity_id: uuid.UUID, user: User, db: AsyncSession
) -> Activity:
    """Resolve an activity the authenticated instructor owns (404 otherwise).

    Mirrors ``_owned_checkpoint`` — a non-owner (or a missing / soft-deleted
    activity / course) is a 404 so course existence is never leaked.
    """
    act = await db.get(Activity, activity_id)
    if act is None or act.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Activity not found")
    course = await db.get(Course, act.course_id)
    if (
        course is None
        or course.deleted_at is not None
        or course.instructor_id != user.id
    ):
        raise HTTPException(status_code=404, detail="Activity not found")
    return act


def _assert_activity_transition(from_status: str, to_status: str) -> None:
    """Assert an activity status edge, else a typed ``ACTIVITY_NOT_PUBLISHABLE``."""
    if to_status not in _ACTIVITY_TRANSITIONS.get(from_status, frozenset()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ACTIVITY_NOT_PUBLISHABLE",
                "message": (
                    f"Cannot move an activity from '{from_status}' to "
                    f"'{to_status}'."
                ),
            },
        )


# ----- create + list (course-scoped) -----


@course_router.post(
    "/activities",
    response_model=APIResponse[ActivityRead],
    status_code=201,
)
async def create_activity(
    body: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[ActivityRead]:
    # Shape-validate the config for this format when one is supplied (a draft may
    # be created config-less and filled in before publish).
    validate_activity_config(body.format, body.config, required=False)

    # Refuse a foreign meeting / score category before persisting anything, so a
    # cross-course id can never be attributed to this course's grade/score records.
    await _validate_activity_refs(
        db,
        course_id=course.id,
        meeting_id=body.meeting_id,
        score_category_id=body.score_category_id,
    )

    act = Activity(
        course_id=course.id,
        meeting_id=body.meeting_id,
        format=body.format,
        title=body.title,
        config=body.config,
        status="draft",
        open_at=body.open_at,
        due_at=body.due_at,
        close_at=body.close_at,
        anonymous=body.anonymous,
        score_category_id=body.score_category_id,
        points=body.points,
        grading_mode=body.grading_mode,
        late_rule=body.late_rule,
        score_bearing=body.score_bearing,
    )
    db.add(act)
    await db.commit()
    await db.refresh(act)
    return APIResponse(success=True, data=ActivityRead.model_validate(act))


@course_router.get(
    "/activities",
    response_model=APIResponse[list[ActivityRead]],
)
async def list_activities(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[ActivityRead]]:
    rows = (
        await db.execute(
            select(Activity)
            .where(
                Activity.course_id == course.id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.created_at)
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[ActivityRead.model_validate(a) for a in rows],
    )


# ----- get / patch / delete (activity-scoped) -----


@router.get(
    "/{activity_id}",
    response_model=APIResponse[ActivityRead],
)
async def get_activity(
    activity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ActivityRead]:
    act = await _owned_activity(activity_id, user, db)
    return APIResponse(success=True, data=ActivityRead.model_validate(act))


@router.patch(
    "/{activity_id}",
    response_model=APIResponse[ActivityRead],
)
async def update_activity(
    activity_id: uuid.UUID,
    body: ActivityUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ActivityRead]:
    act = await _owned_activity(activity_id, user, db)
    fields = body.model_dump(exclude_unset=True)

    # Validate the resulting stored config against the effective format (a patch
    # may change either the config or — future — the format).
    if "config" in fields:
        effective_format = fields.get("format", act.format)
        validate_activity_config(
            effective_format, fields["config"], required=False
        )

    # Refuse a foreign meeting / score category before persisting the patch (only
    # the fields actually supplied are re-validated; an explicit ``None`` unassign
    # is allowed).
    await _validate_activity_refs(
        db,
        course_id=act.course_id,
        meeting_id=fields.get("meeting_id"),
        score_category_id=fields.get("score_category_id"),
    )

    for field, value in fields.items():
        setattr(act, field, value)

    await db.commit()
    await db.refresh(act)
    return APIResponse(success=True, data=ActivityRead.model_validate(act))


@router.delete(
    "/{activity_id}",
    response_model=APIResponse[None],
)
async def delete_activity(
    activity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[None]:
    act = await _owned_activity(activity_id, user, db)
    act.deleted_at = _utcnow()
    await db.commit()
    return APIResponse(success=True, data=None)


# ----- publish (activity-scoped) -----


@router.post(
    "/{activity_id}/publish",
    response_model=APIResponse[ActivityRead],
)
async def publish_activity(
    activity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ActivityRead]:
    """Publish an activity → write an ``activity`` work_item transactionally.

    A SCORE-BEARING activity is GATED: ``assert_score_policy_complete`` raises
    ``SCORE_POLICY_INCOMPLETE`` (422) BEFORE any state flip, so nothing is
    published and no work_item is written (atomicity). A participation-only
    activity SKIPS the gate. The publish is a ``draft→published`` edge;
    re-publishing an already-``published`` activity is an idempotent no-op that
    still re-syncs the work_item.
    """
    act = await _owned_activity(activity_id, user, db)

    # A publishable activity must carry its renderable payload (Decision: config
    # is required at publish, else the student flow has nothing to render).
    validate_activity_config(act.format, act.config, required=True)

    # Gate BEFORE flipping any state so a refusal is fully atomic (mirror B5).
    if act.score_bearing:
        assert_score_policy_complete(act)

    if act.status == "draft":
        _assert_activity_transition(act.status, "published")
        act.status = "published"
    elif act.status == "published":
        pass  # idempotent re-publish — fall through to re-sync the work_item.
    else:
        # live/closed/archived cannot be (re)published.
        _assert_activity_transition(act.status, "published")

    # Transactional checklist-spine write (P4 B4, Decision 4): the work_item
    # rides publish's OWN commit below, so a failure here rolls back the publish
    # too. ``required``/``score_bearing`` come from the activity — a
    # participation-only activity is ``required=False`` so
    # ``mark_missed_work_items`` never marks it missed (Decision 8). Idempotent
    # on the (course, source_kind, source) unique index.
    work_item = await upsert_work_item(
        db,
        course_id=act.course_id,
        source_kind="activity",
        source_id=act.id,
        title=act.title,
        required=act.score_bearing,
        score_bearing=act.score_bearing,
        due_at=act.due_at,
        close_at=act.close_at,
        created_by=user.id,
    )
    # ``on_conflict_do_nothing`` returns the EXISTING row unchanged on
    # re-publish; keep due_at/close_at/title in sync with the activity's current
    # schedule (choice b) so an edited deadline / retitle tracks on the
    # checklist — mirror ``publish_checkpoint``.
    if work_item.due_at != act.due_at:
        work_item.due_at = act.due_at
    if work_item.close_at != act.close_at:
        work_item.close_at = act.close_at
    if work_item.title != act.title:
        work_item.title = act.title

    await db.commit()
    await db.refresh(act)
    return APIResponse(success=True, data=ActivityRead.model_validate(act))


# ----- student response submission (B9) -----


def _activity_not_open(message: str) -> HTTPException:
    """A typed ``ACTIVITY_NOT_OPEN`` gate refusal (§3.4), HTTP 409.

    The student flow (F9) switches on this to render the "waiting / closed"
    states rather than a generic error.
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "ACTIVITY_NOT_OPEN", "message": message},
    )


async def _open_activity_for_student(
    activity_id: uuid.UUID, user: User, db: AsyncSession
) -> Activity:
    """Resolve an activity a student may currently answer.

    404 when it doesn't exist / is soft-deleted; 403 when the caller isn't
    actively enrolled (``verify_enrollment``); ``ACTIVITY_NOT_OPEN`` (409) when
    it isn't ``published``/``live``.
    """
    act = await db.get(Activity, activity_id)
    if act is None or act.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Activity not found")
    await verify_enrollment(db, act.course_id, user.id)
    if act.status not in OPEN_STATUSES:
        raise _activity_not_open("This activity is not open.")
    return act


@router.get(
    "/{activity_id}/intro",
    response_model=APIResponse[ActivityIntro],
)
async def get_activity_intro(
    activity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[ActivityIntro]:
    """Student-facing read of an OPEN activity's public shape (F9 runner).

    Enrollment-scoped (``verify_enrollment``, active-only) and gated to
    ``published``/``live`` — the SAME guard as the B9 response-submit endpoint
    (``_open_activity_for_student``): 404 when it doesn't exist, 403 when the
    caller isn't actively enrolled, ``ACTIVITY_NOT_OPEN`` (409) for a
    draft/closed/archived activity. The owner CRUD read (``GET /activities/{id}``)
    is untouched and still reads ANY status. Returns the slim ``ActivityIntro``
    projection so no owner-internal columns leak (activities carry no answer key).
    """
    act = await _open_activity_for_student(activity_id, user, db)
    return APIResponse(success=True, data=ActivityIntro.model_validate(act))


@router.post(
    "/{activity_id}/responses",
    response_model=APIResponse[ActivityResponseResult],
    status_code=201,
)
async def submit_response(
    activity_id: uuid.UUID,
    body: ActivityResponseSubmit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[ActivityResponseResult]:
    """Upsert this student's activity submission + fire the participation seam.

    Enrollment-scoped (``verify_enrollment``, active-only); the ``user_id`` is the
    authenticated caller, so a student can only ever write their own row.
    """
    act = await _open_activity_for_student(activity_id, user, db)
    response = await submit_activity_response(
        db,
        activity=act,
        user_id=user.id,
        payload=body.payload,
    )
    return APIResponse(
        success=True, data=ActivityResponseResult.model_validate(response)
    )


@router.get(
    "/{activity_id}/results",
    response_model=APIResponse[ActivityResults],
)
async def get_activity_results(
    activity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ActivityResults]:
    """Teacher evidence/aggregate view for an activity (owner-guarded).

    The privileged app connection sees every student's submission; a student gets
    403 (``require_instructor``), a non-owner instructor 404 (``_owned_activity``).
    """
    act = await _owned_activity(activity_id, user, db)
    rows = (
        await db.execute(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == act.id
            )
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=ActivityResults(
            activity_id=act.id,
            format=act.format,
            status=act.status,
            submission_count=len(rows),
            responses=[ActivityResponseResult.model_validate(r) for r in rows],
        ),
    )


# ----- teacher live monitor WebSocket (P5 B10, Decision 6) -----
#
# Reuses the live-quiz ``ConnectionManager`` class via ``monitor_manager`` — no
# new WS framework. Auth preamble is copied from ``checkpoints.py``'s
# ``websocket_monitor`` (``?token=`` → ``verify_jwt`` → resolve user), keeping the
# OWNER check: only the activity's course instructor may monitor. The monitor is
# read-only — inbound frames are drained and ignored; the server only ever pushes
# ``state``/``submission``/``closed``.


@router.websocket("/{activity_id}/monitor")
async def websocket_monitor(
    websocket: WebSocket,
    activity_id: str,
    token: str = "",
):
    """Teacher live-monitor stream for one activity.

    On connect the owner receives ``{type: "state", submission_count,
    distribution}``; thereafter the hub pushes ``submission`` (a student response
    landed) and ``closed`` (the activity closed) broadcasts.
    """
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        verified = verify_jwt(token)
    except Exception as exc:  # noqa: BLE001 — any verify failure is a policy reject
        logger.warning("Monitor WS auth failed for activity %s: %s", activity_id, exc)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    auth_user_id = verified.claims.get("sub")
    if not auth_user_id:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    try:
        act_uuid = uuid.UUID(activity_id)
    except ValueError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    # Resolve user + OWNER-guard the activity, then snapshot the initial state —
    # all in one short-lived session that is released before the read-loop.
    async with async_session_factory() as db:
        user = (
            await db.execute(
                select(User).where(User.better_auth_id == auth_user_id)
            )
        ).scalar_one_or_none()
        if user is None:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

        act = await db.get(Activity, act_uuid)
        if act is None or act.deleted_at is not None:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        course = await db.get(Course, act.course_id)
        if (
            course is None
            or course.deleted_at is not None
            or course.instructor_id != user.id
        ):
            # Owner-only: a non-owner (or student) is rejected before accept.
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

        initial_state = await compute_activity_monitor_state(db, act_uuid)

    await monitor_manager.connect(activity_id, websocket)
    try:
        await websocket.send_json({"type": "state", **initial_state})
        # Read-only monitor: drain (and ignore) inbound frames until disconnect.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        monitor_manager.disconnect(activity_id, websocket)
