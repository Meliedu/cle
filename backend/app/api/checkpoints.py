"""Checkpoints router (Task 9): teacher generation + DRAFT-only card CRUD.

Decision 3 — P1 writes/exposes ``draft``/``teacher_editing`` states ONLY. There
are deliberately NO publish/approve/schedule/close routes here (those ship P3);
a test asserts they 404. The single ``final_comments`` card is fixed (not
removable); removing a ``review_point`` requires a reason; card edits are only
allowed while the checkpoint is in an editable draft state.

Two routers are exported:
- ``course_router`` under ``/courses/{course_id}/checkpoints`` (generate + list),
  guarded by ``get_owned_course``.
- ``router`` under ``/checkpoints`` (get/delete + card CRUD), guarded by a
  per-checkpoint ownership helper that mirrors ``get_owned_course`` semantics
  (404 on non-owner, never 403, so course existence isn't leaked).
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment as _verify_enrollment
from app.api.deps import (
    get_current_user,
    get_owned_course,
    require_instructor,
    require_student,
)
from app.database import async_session_factory, get_db
from app.models.checkpoint import (
    Checkpoint,
    CheckpointCard,
    CheckpointResponse as CheckpointResponseModel,
)
from app.models.concept import Concept, ConceptTag
from app.models.course import Course, Enrollment
from app.models.task import Task
from app.models.user import User
from app.schemas.checkpoint import (
    CheckpointCardCreate,
    CheckpointCardResponse,
    CheckpointCardResult,
    CheckpointCardUpdate,
    CheckpointGenerateRequest,
    CheckpointIntroResponse,
    CheckpointPublishRequest,
    CheckpointResponse,
    CheckpointResponseResult,
    CheckpointResponseSubmit,
    CheckpointResults,
    CheckpointScheduleRequest,
    FollowUpSuggested,
    FollowUpSuggestedCard,
    RevisitResponseResult,
    StudentCheckpointCard,
    StudentCheckpointHistoryItem,
    CheckpointWithCardsResponse,
)
from app.schemas.common import APIResponse
from app.services.auth import verify_jwt
from app.services.checkpoint_monitor import (
    broadcast_closed,
    compute_monitor_state,
    monitor_manager,
)
from app.services.checkpoint_responses import (
    OPEN_STATUSES,
    is_within_window,
    submit_checkpoint_response,
)
from app.services.checkpoints import IllegalTransition, assert_transition

logger = logging.getLogger(__name__)

# Card mutations (edit/remove/add) are only legal while the teacher is still
# drafting (Decision 3). Any later state is P3 territory and refuses edits.
_EDITABLE_STATUSES = {"draft", "teacher_editing"}

# The history filter (P3 T6, T049) surfaces checkpoints that have run their
# course. Anything still in flight (draft…live) is excluded.
_HISTORY_STATUSES = ("closed", "archived")

# The −2..+2 confidence scale buckets (pilot ``ConfidenceScale``); every bucket
# is present (zero-filled) in a review_point card's distribution so the T048/T019
# histogram renders a stable axis.
_CONFIDENCE_BUCKETS = (-2, -1, 0, 1, 2)

router = APIRouter(prefix="/checkpoints", tags=["checkpoints"])
course_router = APIRouter(prefix="/courses/{course_id}", tags=["checkpoints"])
# Student self-scoped router (``/users/me/...``) — mirrors ``api/mastery.py``'s
# path shape. No prefix; the enrollment guard lives in the handler.
student_router = APIRouter(tags=["checkpoints"])

# Checkpoint lifecycle states a student can ever see in their history (S039).
# Anything still being drafted by the teacher is invisible to students.
_STUDENT_VISIBLE_STATUSES = ("published", "live", "closed", "archived")

# A checkpoint is "closed" for the student once it reaches a terminal state.
_CLOSED_STATUSES = frozenset({"closed", "archived"})

# Low-confidence threshold for the suggested follow-up (S040). On the −2..+2
# ConfidenceScale, −2 ("no idea") and −1 ("shaky") are the weak buckets; a
# response at or below −1 is surfaced as a card to revisit.
_LOW_CONFIDENCE_THRESHOLD = -1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _owned_checkpoint(
    checkpoint_id: uuid.UUID, user: User, db: AsyncSession
) -> Checkpoint:
    """Resolve a checkpoint the authenticated instructor owns (404 otherwise)."""
    cp = await db.get(Checkpoint, checkpoint_id)
    if cp is None or cp.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    course = await db.get(Course, cp.course_id)
    if course is None or course.deleted_at is not None or course.instructor_id != user.id:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return cp


def _assert_editable(cp: Checkpoint) -> None:
    if cp.status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                # Spec typed-error taxonomy (§3.4): the FE switches on
                # SETUP_INCOMPLETE | SETUP_NOT_OPEN | FINAL_CARD_FIXED |
                # REVIEW_REQUIRED, so this must be REVIEW_REQUIRED.
                "code": "REVIEW_REQUIRED",
                "message": (
                    f"Checkpoint is '{cp.status}'; cards can only be edited while "
                    "it is a draft."
                ),
            },
        )


def _bump_editing(cp: Checkpoint) -> None:
    """A teacher edit moves a fresh ``draft`` into ``teacher_editing`` (§4.2)."""
    if cp.status == "draft":
        cp.status = "teacher_editing"


async def _load_cards(db: AsyncSession, checkpoint_id: uuid.UUID) -> list[CheckpointCard]:
    return list(
        (
            await db.execute(
                select(CheckpointCard)
                .where(
                    CheckpointCard.checkpoint_id == checkpoint_id,
                    CheckpointCard.deleted_at.is_(None),
                )
                .order_by(CheckpointCard.position)
            )
        ).scalars().all()
    )


# ----- generate + list (course-scoped) -----

@course_router.post(
    "/checkpoints/generate", response_model=APIResponse[None], status_code=202
)
async def generate_checkpoints(
    body: CheckpointGenerateRequest,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[None]:
    """Enqueue the grounded ``generate_checkpoints`` job (Task 6). DRAFT-only."""
    payload: dict[str, str | int] = {"course_id": str(course.id)}
    if body.meeting_id is not None:
        payload["meeting_id"] = str(body.meeting_id)
    if body.review_card_count is not None:
        payload["review_card_count"] = body.review_card_count
    db.add(Task(task_type="generate_checkpoints", payload=payload, status="pending"))
    await db.commit()
    return APIResponse(success=True, data=None)


@course_router.get(
    "/checkpoints", response_model=APIResponse[list[CheckpointResponse]]
)
async def list_checkpoints(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
    history: bool = Query(
        default=False,
        description=(
            "When truthy, list only closed/archived checkpoints (the T049 "
            "history view). Absent/0 preserves the P1 behaviour (all live rows)."
        ),
    ),
) -> APIResponse[list[CheckpointResponse]]:
    stmt = (
        select(Checkpoint)
        .where(
            Checkpoint.course_id == course.id,
            Checkpoint.deleted_at.is_(None),
        )
        .order_by(Checkpoint.created_at)
    )
    # The history filter is additive (Decision: reality beats plan) — without it
    # the P1 contract (every non-deleted checkpoint) is unchanged.
    if history:
        stmt = stmt.where(Checkpoint.status.in_(_HISTORY_STATUSES))
    rows = (await db.execute(stmt)).scalars().all()
    return APIResponse(
        success=True,
        data=[CheckpointResponse.model_validate(cp) for cp in rows],
    )


# ----- get / delete (checkpoint-scoped) -----

@router.get("/{checkpoint_id}", response_model=APIResponse[CheckpointWithCardsResponse])
async def get_checkpoint(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[CheckpointWithCardsResponse]:
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    # Ensure onupdate-managed columns (updated_at) are populated before
    # serialization — a prior card edit in the same session expires them.
    await db.refresh(cp)
    cards = await _load_cards(db, cp.id)
    data = CheckpointWithCardsResponse.model_validate(cp)
    data.cards = [CheckpointCardResponse.model_validate(c) for c in cards]
    return APIResponse(success=True, data=data)


@router.get(
    "/{checkpoint_id}/results", response_model=APIResponse[CheckpointResults]
)
async def get_checkpoint_results(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CheckpointResults]:
    """Teacher results for a checkpoint (P3 T6, T048/T019).

    Per-card response counts + a −2..+2 confidence histogram for ``review_point``
    cards, plus a derived "missed" count = active-enrolled students with no
    response (only meaningful once the checkpoint is closed). Owner-guarded
    course-scoped read (Decision 2) — the privileged app connection sees every
    student's response; a student gets 403, a non-owner instructor 404.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    cards = await _load_cards(db, cp.id)

    responses = (
        await db.execute(
            select(CheckpointResponseModel).where(
                CheckpointResponseModel.checkpoint_id == cp.id
            )
        )
    ).scalars().all()

    by_card: dict[uuid.UUID, list[CheckpointResponseModel]] = {}
    responded_user_ids: set[uuid.UUID] = set()
    for resp in responses:
        by_card.setdefault(resp.card_id, []).append(resp)
        responded_user_ids.add(resp.user_id)

    card_results: list[CheckpointCardResult] = []
    for card in cards:
        card_responses = by_card.get(card.id, [])
        if card.kind == "review_point":
            distribution = {str(b): 0 for b in _CONFIDENCE_BUCKETS}
            for resp in card_responses:
                if resp.confidence is not None:
                    key = str(resp.confidence)
                    if key in distribution:
                        distribution[key] += 1
            text_count = 0
        else:
            distribution = {}
            text_count = sum(
                1 for r in card_responses if r.text_response is not None
            )
        card_results.append(
            CheckpointCardResult(
                card_id=card.id,
                kind=card.kind,
                prompt=card.prompt,
                position=card.position,
                response_count=len(card_responses),
                confidence_distribution=distribution,
                text_response_count=text_count,
            )
        )

    # Active-student roster is the "missed" denominator (Enrollment status=active,
    # role=student — instructors/pending rows never count).
    active_student_ids = set(
        (
            await db.execute(
                select(Enrollment.user_id).where(
                    Enrollment.course_id == cp.course_id,
                    Enrollment.status == "active",
                    Enrollment.role == "student",
                )
            )
        ).scalars().all()
    )
    responded_active = active_student_ids & responded_user_ids
    missed = len(active_student_ids - responded_user_ids)

    return APIResponse(
        success=True,
        data=CheckpointResults(
            checkpoint_id=cp.id,
            status=cp.status,
            active_student_count=len(active_student_ids),
            responded_count=len(responded_active),
            missed_count=missed,
            cards=card_results,
        ),
    )


@router.delete("/{checkpoint_id}", response_model=APIResponse[None])
async def delete_checkpoint(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[None]:
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    cp.deleted_at = _utcnow()
    await db.commit()
    return APIResponse(success=True, data=None)


# ----- card CRUD (checkpoint-scoped, DRAFT-only) -----

async def _load_card(
    db: AsyncSession, cp: Checkpoint, card_id: uuid.UUID
) -> CheckpointCard:
    card = await db.get(CheckpointCard, card_id)
    if (
        card is None
        or card.deleted_at is not None
        or card.checkpoint_id != cp.id
    ):
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.patch(
    "/{checkpoint_id}/cards/{card_id}",
    response_model=APIResponse[CheckpointCardResponse],
)
async def update_card(
    checkpoint_id: uuid.UUID,
    card_id: uuid.UUID,
    body: CheckpointCardUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[CheckpointCardResponse]:
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    _assert_editable(cp)
    card = await _load_card(db, cp, card_id)
    fields = body.model_dump(exclude_unset=True)

    if fields.get("removed") is True:
        # The final_comments card is fixed — it can never be removed (§4.2).
        if card.kind == "final_comments":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "FINAL_CARD_FIXED",
                    "message": "The final comments card cannot be removed.",
                },
            )
        # Removing a review_point requires a categorized reason.
        reason = fields.get("removed_reason") or card.removed_reason
        if not reason:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REMOVE_REASON_REQUIRED",
                    "message": "A removal reason is required to remove a card.",
                },
            )
        card.removed = True
        card.removed_reason = reason
        if "removed_note" in fields:
            card.removed_note = fields["removed_note"]
        # Soft-remove so the partial unique index / list queries skip it.
        card.deleted_at = _utcnow()
    else:
        # No un-remove branch: removing soft-deletes (deleted_at), and
        # _load_card 404s on deleted_at, so a removed card can never be edited
        # back. Un-remove is a P3 concern once card history is exposed.
        for field in ("prompt", "document_id", "chunk_id", "objective_id", "removed_note"):
            if field in fields:
                setattr(card, field, fields[field])

    _bump_editing(cp)
    await db.commit()
    await db.refresh(card)  # pull the onupdate-refreshed updated_at
    return APIResponse(success=True, data=CheckpointCardResponse.model_validate(card))


@router.post(
    "/{checkpoint_id}/cards",
    response_model=APIResponse[CheckpointCardResponse],
    status_code=201,
)
async def add_card(
    checkpoint_id: uuid.UUID,
    body: CheckpointCardCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[CheckpointCardResponse]:
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    _assert_editable(cp)

    if body.position is not None:
        position = body.position
    else:
        # Append after the current max position among live cards.
        existing = await _load_cards(db, cp.id)
        position = (max((c.position for c in existing), default=-1)) + 1

    # kind is server-forced to review_point — the single final_comments card is
    # fixed and never created via this endpoint (respects the partial unique
    # index uq_checkpoint_cards_one_final).
    card = CheckpointCard(
        checkpoint_id=cp.id,
        position=position,
        kind="review_point",
        prompt=body.prompt,
        document_id=body.document_id,
        chunk_id=body.chunk_id,
        objective_id=body.objective_id,
    )
    db.add(card)
    _bump_editing(cp)
    await db.commit()
    await db.refresh(card)  # pull the server-generated created_at/updated_at
    return APIResponse(success=True, data=CheckpointCardResponse.model_validate(card))


# ----- publish path: approve / schedule / publish / close (P3 T5) -----
#
# Every state change routes through ``assert_transition`` (the T1 service — the
# single source of truth for legal edges, Decision 1). T1's map deliberately
# forbids skip-edges: ``draft→approved`` and ``published→closed`` are illegal, so
# ``approve`` walks ``draft→teacher_editing→approved`` and ``close`` walks
# ``published→live→closed`` — one asserted step at a time.
#
# ``review_actions`` audit note: the repo's ``review_actions`` table
# (``models/evidence.py``) is the reviewed-evidence loop's append-only log and is
# hard-bound to a ``learning_note_id`` with an ``action_type`` CHECK that has no
# checkpoint verbs, so it cannot hold publish-path transitions. T5 is scoped to
# the router (no migration), so the transition audit trail is appended to
# ``checkpoint.generation_meta['review_actions']`` — an immutable-style list of
# ``{action, from, to, actor_id, at}`` entries.


def _review_required(message: str) -> HTTPException:
    """A typed ``REVIEW_REQUIRED`` gate refusal (§3.4), HTTP 409."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "REVIEW_REQUIRED", "message": message},
    )


def _apply_transition(cp: Checkpoint, *targets: str) -> None:
    """Walk ``cp.status`` through each target, asserting every edge via T1.

    Any illegal edge raises ``IllegalTransition`` which the caller maps to a
    ``REVIEW_REQUIRED`` 409.
    """
    for target in targets:
        assert_transition(cp.status, target)
        cp.status = target


def _append_review_action(
    cp: Checkpoint, action: str, from_status: str, actor_id: uuid.UUID
) -> None:
    """Append an audit entry to ``generation_meta['review_actions']``.

    Immutable update: a fresh dict/list is assigned so SQLAlchemy flags the
    JSONB column dirty (in-place mutation would not be detected).
    """
    meta = dict(cp.generation_meta or {})
    actions = list(meta.get("review_actions", []))
    actions.append(
        {
            "action": action,
            "from": from_status,
            "to": cp.status,
            "actor_id": str(actor_id),
            "at": _utcnow().isoformat(),
        }
    )
    meta["review_actions"] = actions
    cp.generation_meta = meta


@router.post("/{checkpoint_id}/approve", response_model=APIResponse[CheckpointResponse])
async def approve_checkpoint(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CheckpointResponse]:
    """``draft``/``teacher_editing`` → ``approved`` (§4.2).

    Gate: at least one non-removed ``review_point`` card AND the fixed
    ``final_comments`` card must be present, else ``REVIEW_REQUIRED``.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    from_status = cp.status

    cards = await _load_cards(db, cp.id)
    review_points = [
        c for c in cards if c.kind == "review_point" and not c.removed
    ]
    finals = [c for c in cards if c.kind == "final_comments"]
    if not review_points or not finals:
        raise _review_required(
            "A checkpoint needs at least one review point and the final "
            "comments card before it can be approved."
        )

    try:
        # draft→approved is a skip-edge (illegal in T1); walk via teacher_editing.
        if cp.status == "draft":
            _apply_transition(cp, "teacher_editing", "approved")
        else:
            _apply_transition(cp, "approved")
    except IllegalTransition as exc:
        raise _review_required(exc.message) from exc

    _append_review_action(cp, "approve", from_status, user.id)
    await db.commit()
    await db.refresh(cp)
    return APIResponse(success=True, data=CheckpointResponse.model_validate(cp))


@router.post("/{checkpoint_id}/schedule", response_model=APIResponse[CheckpointResponse])
async def schedule_checkpoint(
    checkpoint_id: uuid.UUID,
    body: CheckpointScheduleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CheckpointResponse]:
    """``approved`` → ``scheduled`` (§4.2).

    Gate: ``release_at`` and ``close_rule`` must be set (from the body, falling
    back to any values already on the checkpoint), else ``REVIEW_REQUIRED``.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    from_status = cp.status

    if body.release_at is not None:
        cp.release_at = body.release_at
    if body.close_at is not None:
        cp.close_at = body.close_at
    if body.close_rule is not None:
        cp.close_rule = body.close_rule

    if cp.release_at is None or cp.close_rule is None:
        raise _review_required(
            "A release time and close rule are required to schedule a checkpoint."
        )

    try:
        _apply_transition(cp, "scheduled")
    except IllegalTransition as exc:
        raise _review_required(exc.message) from exc

    _append_review_action(cp, "schedule", from_status, user.id)
    await db.commit()
    await db.refresh(cp)
    return APIResponse(success=True, data=CheckpointResponse.model_validate(cp))


@router.post("/{checkpoint_id}/publish", response_model=APIResponse[CheckpointResponse])
async def publish_checkpoint(
    checkpoint_id: uuid.UUID,
    body: CheckpointPublishRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CheckpointResponse]:
    """``approved``/``scheduled`` → ``published`` (§4.2).

    Gate (all required, else ``REVIEW_REQUIRED``): a session relation
    (``meeting_id``), release timing (``release_at``) and a close rule
    (``close_rule``). Illegal source states are refused by ``assert_transition``.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    from_status = cp.status

    if body is not None:
        if body.release_at is not None:
            cp.release_at = body.release_at
        if body.close_at is not None:
            cp.close_at = body.close_at
        if body.close_rule is not None:
            cp.close_rule = body.close_rule

    if cp.meeting_id is None:
        raise _review_required(
            "A checkpoint must be attached to a session before it can be published."
        )
    if cp.release_at is None or cp.close_rule is None:
        raise _review_required(
            "A release time and close rule are required to publish a checkpoint."
        )

    try:
        _apply_transition(cp, "published")
    except IllegalTransition as exc:
        raise _review_required(exc.message) from exc

    _append_review_action(cp, "publish", from_status, user.id)
    await db.commit()
    await db.refresh(cp)
    return APIResponse(success=True, data=CheckpointResponse.model_validate(cp))


@router.post("/{checkpoint_id}/close", response_model=APIResponse[CheckpointResponse])
async def close_checkpoint(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CheckpointResponse]:
    """``published``/``live`` → ``closed`` (§4.2).

    ``published→closed`` is a skip-edge (illegal in T1), so a publish that never
    went ``live`` is walked ``published→live→closed`` — each step asserted.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    from_status = cp.status

    try:
        if cp.status == "published":
            _apply_transition(cp, "live", "closed")
        else:
            _apply_transition(cp, "closed")
    except IllegalTransition as exc:
        raise _review_required(exc.message) from exc

    _append_review_action(cp, "close", from_status, user.id)
    await db.commit()
    await db.refresh(cp)

    # Best-effort: tell any connected live monitor the checkpoint closed. A
    # broadcast failure must never fail the close (the state change is durable).
    try:
        await broadcast_closed(db, cp.id)
    except Exception:  # noqa: BLE001 — non-fatal: close already committed
        logger.exception("monitor closed-broadcast failed for checkpoint_id=%s", cp.id)

    return APIResponse(success=True, data=CheckpointResponse.model_validate(cp))


# ----- student intro + response submission (P3 T7, S034–S036) -----
#
# Student-facing, enrollment-scoped (NOT owner). The evidence seam lives in
# ``services/checkpoint_responses.py`` and mirrors ``quizzes.py`` exactly
# (Decision 5): one LearningEvent(during_class) + an update_concept_mastery
# Task for concept-tagged review_point cards, best-effort.


def _qr_not_available(message: str) -> HTTPException:
    """A typed ``QR_NOT_AVAILABLE`` gate refusal (§3.4), HTTP 409.

    The mobile flow (S034/S038) switches on this to render the "not open yet /
    missed" states rather than a generic error.
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "QR_NOT_AVAILABLE", "message": message},
    )


async def _open_checkpoint_for_student(
    checkpoint_id: uuid.UUID, user: User, db: AsyncSession
) -> Checkpoint:
    """Resolve a checkpoint a student may currently answer.

    404 when it doesn't exist; 403 when the student isn't actively enrolled;
    ``QR_NOT_AVAILABLE`` (409) when it isn't ``published``/``live``.
    """
    cp = await db.get(Checkpoint, checkpoint_id)
    if cp is None or cp.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    await _verify_enrollment(db, cp.course_id, user.id)
    if cp.status not in OPEN_STATUSES:
        raise _qr_not_available("This checkpoint is not open.")
    return cp


@router.get(
    "/{checkpoint_id}/intro",
    response_model=APIResponse[CheckpointIntroResponse],
)
async def get_checkpoint_intro(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[CheckpointIntroResponse]:
    """Student intro: the ordered live cards, only while open + in window."""
    cp = await _open_checkpoint_for_student(checkpoint_id, user, db)
    if not is_within_window(cp, _utcnow()):
        raise _qr_not_available("This checkpoint is not open right now.")
    cards = await _load_cards(db, cp.id)
    return APIResponse(
        success=True,
        data=CheckpointIntroResponse(
            checkpoint_id=cp.id,
            title=cp.title,
            status=cp.status,
            close_at=cp.close_at,
            cards=[StudentCheckpointCard.model_validate(c) for c in cards],
        ),
    )


@router.post(
    "/{checkpoint_id}/responses",
    response_model=APIResponse[CheckpointResponseResult],
    status_code=201,
)
async def submit_response(
    checkpoint_id: uuid.UUID,
    body: CheckpointResponseSubmit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[CheckpointResponseResult]:
    """Upsert one card's answer + fire the evidence seam (service layer).

    A card_id that belongs to a *different* checkpoint is a 404 (the T2
    consistency check) — never silently accepted against this checkpoint.
    """
    cp = await _open_checkpoint_for_student(checkpoint_id, user, db)

    card = await db.get(CheckpointCard, body.card_id)
    if (
        card is None
        or card.deleted_at is not None
        or card.checkpoint_id != cp.id
    ):
        raise HTTPException(status_code=404, detail="Card not found")

    response = await submit_checkpoint_response(
        db,
        checkpoint=cp,
        card=card,
        user_id=user.id,
        confidence=body.confidence,
        text_response=body.text_response,
    )
    return APIResponse(
        success=True, data=CheckpointResponseResult.model_validate(response)
    )


# ----- student history + follow-up + revisit (P3 T8, S039–S041) -----
#
# Student-facing, enrollment-scoped (the student's own data only — RLS is
# defense-in-depth; the endpoint guard is `_verify_enrollment` → 403). Nothing
# here reads another student's rows.


def _derive_history_status(
    cp_status: str, live_card_count: int, responses: list[CheckpointResponseModel]
) -> str:
    """Derive the student's per-checkpoint status (S039).

    * ``missed`` — the checkpoint is closed and the student never responded.
    * ``upcoming`` — the checkpoint is still open and the student hasn't yet
      answered every live card.
    * ``late`` — any response arrived late, OR the checkpoint closed while the
      student had only partially answered.
    * ``complete`` — the student answered every live card, none of them late.
    """
    closed = cp_status in _CLOSED_STATUSES
    if not responses:
        return "missed" if closed else "upcoming"
    if any(r.status == "late" for r in responses):
        return "late"
    answered_all = len(responses) >= live_card_count and live_card_count > 0
    if answered_all:
        return "complete"
    # Partial answers: late once the window has closed, still upcoming while open.
    return "late" if closed else "upcoming"


@student_router.get(
    "/users/me/courses/{course_id}/checkpoints",
    response_model=APIResponse[list[StudentCheckpointHistoryItem]],
)
async def my_checkpoint_history(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[list[StudentCheckpointHistoryItem]]:
    """The student's own checkpoint history for a course (S039).

    Enrollment-scoped (403 for a non-enrolled user). Draft/teacher-editing
    checkpoints are invisible; every visible checkpoint carries a derived
    per-student status.
    """
    await _verify_enrollment(db, course_id, user.id)

    checkpoints = list(
        (
            await db.execute(
                select(Checkpoint)
                .where(
                    Checkpoint.course_id == course_id,
                    Checkpoint.deleted_at.is_(None),
                    Checkpoint.status.in_(_STUDENT_VISIBLE_STATUSES),
                )
                .order_by(Checkpoint.created_at)
            )
        ).scalars().all()
    )
    if not checkpoints:
        return APIResponse(success=True, data=[])

    cp_ids = [cp.id for cp in checkpoints]

    # Live (non-removed) card counts per checkpoint — the "answered all" denom.
    live_cards = (
        await db.execute(
            select(CheckpointCard.checkpoint_id).where(
                CheckpointCard.checkpoint_id.in_(cp_ids),
                CheckpointCard.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    live_count_by_cp: dict[uuid.UUID, int] = {}
    for cp_id in live_cards:
        live_count_by_cp[cp_id] = live_count_by_cp.get(cp_id, 0) + 1

    # This student's responses across those checkpoints (their own rows only).
    responses = (
        await db.execute(
            select(CheckpointResponseModel).where(
                CheckpointResponseModel.checkpoint_id.in_(cp_ids),
                CheckpointResponseModel.user_id == user.id,
            )
        )
    ).scalars().all()
    resp_by_cp: dict[uuid.UUID, list[CheckpointResponseModel]] = {}
    for resp in responses:
        resp_by_cp.setdefault(resp.checkpoint_id, []).append(resp)

    items = [
        StudentCheckpointHistoryItem(
            checkpoint_id=cp.id,
            title=cp.title,
            kind=cp.kind,
            status=cp.status,
            derived_status=_derive_history_status(
                cp.status,
                live_count_by_cp.get(cp.id, 0),
                resp_by_cp.get(cp.id, []),
            ),
            release_at=cp.release_at,
            close_at=cp.close_at,
            responded_count=len(resp_by_cp.get(cp.id, [])),
            live_card_count=live_count_by_cp.get(cp.id, 0),
        )
        for cp in checkpoints
    ]
    return APIResponse(success=True, data=items)


async def _enrolled_checkpoint_for_student(
    checkpoint_id: uuid.UUID, user: User, db: AsyncSession
) -> Checkpoint:
    """Resolve a checkpoint the student is enrolled to see (404/403 only).

    Unlike ``_open_checkpoint_for_student`` this does NOT require the checkpoint
    to be open — history/follow-up reads are valid against closed checkpoints.
    """
    cp = await db.get(Checkpoint, checkpoint_id)
    if cp is None or cp.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    await _verify_enrollment(db, cp.course_id, user.id)
    return cp


async def _concept_for_card(
    db: AsyncSession, card_id: uuid.UUID
) -> tuple[uuid.UUID | None, str | None]:
    """The (concept_id, concept_name) a checkpoint card is tagged with, if any.

    Returns the highest-weight non-deleted concept tag (a card can carry more
    than one). ``(None, None)`` when the card is untagged.
    """
    row = (
        await db.execute(
            select(ConceptTag.concept_id, Concept.name)
            .join(Concept, Concept.id == ConceptTag.concept_id)
            .where(
                ConceptTag.target_kind == "checkpoint_card",
                ConceptTag.target_id == card_id,
                Concept.deleted_at.is_(None),
            )
            .order_by(ConceptTag.weight.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


@router.get(
    "/{checkpoint_id}/follow-up-suggested",
    response_model=APIResponse[FollowUpSuggested],
)
async def follow_up_suggested(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[FollowUpSuggested]:
    """Suggested follow-up from the student's low-confidence responses (S040).

    Enrollment-scoped. Returns the review cards where the student's own
    confidence fell at or below ``_LOW_CONFIDENCE_THRESHOLD`` (−1), each with
    the tagged concept when present so the follow-up can be built around it.
    """
    cp = await _enrolled_checkpoint_for_student(checkpoint_id, user, db)

    weak_responses = (
        await db.execute(
            select(CheckpointResponseModel, CheckpointCard.prompt)
            .join(
                CheckpointCard, CheckpointCard.id == CheckpointResponseModel.card_id
            )
            .where(
                CheckpointResponseModel.checkpoint_id == cp.id,
                CheckpointResponseModel.user_id == user.id,
                CheckpointResponseModel.confidence.is_not(None),
                CheckpointResponseModel.confidence <= _LOW_CONFIDENCE_THRESHOLD,
                CheckpointCard.deleted_at.is_(None),
            )
            .order_by(CheckpointCard.position)
        )
    ).all()

    weak_cards: list[FollowUpSuggestedCard] = []
    for resp, prompt in weak_responses:
        concept_id, concept_name = await _concept_for_card(db, resp.card_id)
        weak_cards.append(
            FollowUpSuggestedCard(
                card_id=resp.card_id,
                prompt=prompt,
                confidence=resp.confidence,  # type: ignore[arg-type]
                concept_id=concept_id,
                concept_name=concept_name,
            )
        )

    return APIResponse(
        success=True,
        data=FollowUpSuggested(
            checkpoint_id=cp.id,
            threshold=_LOW_CONFIDENCE_THRESHOLD,
            weak_cards=weak_cards,
        ),
    )


def _not_a_revisit(message: str) -> HTTPException:
    """A typed 409 for a checkpoint that can't take a revisit (§3.4)."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "NOT_A_REVISIT", "message": message},
    )


async def _confidence_before(
    db: AsyncSession,
    *,
    carried_from_id: uuid.UUID,
    concept_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> int | None:
    """The student's original confidence on the carried-from checkpoint.

    Matches by shared concept: find the original checkpoint's card tagged with
    ``concept_id`` and return the student's confidence there. ``None`` when the
    revisit card is untagged or the student never answered the original.
    """
    if concept_id is None:
        return None
    row = (
        await db.execute(
            select(CheckpointResponseModel.confidence)
            .join(
                CheckpointCard, CheckpointCard.id == CheckpointResponseModel.card_id
            )
            .join(
                ConceptTag,
                (ConceptTag.target_id == CheckpointCard.id)
                & (ConceptTag.target_kind == "checkpoint_card"),
            )
            .where(
                CheckpointResponseModel.checkpoint_id == carried_from_id,
                CheckpointResponseModel.user_id == user_id,
                ConceptTag.concept_id == concept_id,
                CheckpointResponseModel.confidence.is_not(None),
            )
            .order_by(CheckpointResponseModel.submitted_at)
            .limit(1)
        )
    ).first()
    return row[0] if row is not None else None


@router.post(
    "/{checkpoint_id}/revisit-response",
    response_model=APIResponse[RevisitResponseResult],
    status_code=201,
)
async def revisit_response(
    checkpoint_id: uuid.UUID,
    body: CheckpointResponseSubmit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[RevisitResponseResult]:
    """Re-submit against a ``follow_up`` checkpoint carrying ``carried_from_id``
    → the original (S041).

    Reuses the T7 submission service, then records a before/after confidence
    signal (the student's original response on the carried-from checkpoint vs
    this revisit) matched by shared concept. Enrollment-scoped; a non-follow_up
    or uncarried checkpoint is a typed ``NOT_A_REVISIT`` 409.
    """
    cp = await _open_checkpoint_for_student(checkpoint_id, user, db)
    if cp.kind != "follow_up" or cp.carried_from_id is None:
        raise _not_a_revisit(
            "This checkpoint is not a follow-up revisit of an earlier checkpoint."
        )
    carried_from_id = cp.carried_from_id

    card = await db.get(CheckpointCard, body.card_id)
    if (
        card is None
        or card.deleted_at is not None
        or card.checkpoint_id != cp.id
    ):
        raise HTTPException(status_code=404, detail="Card not found")
    card_id = card.id

    response = await submit_checkpoint_response(
        db,
        checkpoint=cp,
        card=card,
        user_id=user.id,
        confidence=body.confidence,
        text_response=body.text_response,
    )
    confidence_after = response.confidence

    # Before/after: match the original card by the revisit card's concept.
    concept_id, _ = await _concept_for_card(db, card_id)
    confidence_before = await _confidence_before(
        db,
        carried_from_id=carried_from_id,
        concept_id=concept_id,
        user_id=user.id,
    )
    delta = (
        confidence_after - confidence_before
        if confidence_after is not None and confidence_before is not None
        else None
    )

    return APIResponse(
        success=True,
        data=RevisitResponseResult(
            response=CheckpointResponseResult.model_validate(response),
            carried_from_id=carried_from_id,
            concept_id=concept_id,
            confidence_before=confidence_before,
            confidence_after=confidence_after,
            delta=delta,
        ),
    )


# ----- teacher live monitor WebSocket (P3 T12, Decision 4) -----
#
# Reuses the live-quiz ``ConnectionManager`` class via ``monitor_manager`` — no
# new WS framework. Auth preamble is copied from ``api/live.py``'s
# ``websocket_live`` (``?token=`` → ``verify_jwt`` → resolve user), but the
# enrollment check is swapped for an OWNER check: only the checkpoint's course
# instructor may monitor. The monitor is read-only — inbound frames are drained
# and ignored; the server only ever pushes ``state``/``submission``/``closed``.


@router.websocket("/{checkpoint_id}/monitor")
async def websocket_monitor(
    websocket: WebSocket,
    checkpoint_id: str,
    token: str = "",
):
    """Teacher live-monitor stream for one checkpoint.

    On connect the owner receives ``{type: "state", submission_count,
    confidence_distribution}``; thereafter the hub pushes ``submission`` (a
    student response landed) and ``closed`` (the checkpoint closed) broadcasts.
    """
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        verified = verify_jwt(token)
    except Exception as exc:  # noqa: BLE001 — any verify failure is a policy reject
        logger.warning("Monitor WS auth failed for checkpoint %s: %s", checkpoint_id, exc)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    auth_user_id = verified.claims.get("sub")
    if not auth_user_id:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    try:
        cp_uuid = uuid.UUID(checkpoint_id)
    except ValueError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    # Resolve user + OWNER-guard the checkpoint, then snapshot the initial state
    # — all in one short-lived session that is released before the read-loop.
    async with async_session_factory() as db:
        user = (
            await db.execute(
                select(User).where(User.better_auth_id == auth_user_id)
            )
        ).scalar_one_or_none()
        if user is None:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

        cp = await db.get(Checkpoint, cp_uuid)
        if cp is None or cp.deleted_at is not None:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        course = await db.get(Course, cp.course_id)
        if (
            course is None
            or course.deleted_at is not None
            or course.instructor_id != user.id
        ):
            # Owner-only: a non-owner (or student) is rejected before accept.
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

        initial_state = await compute_monitor_state(db, cp_uuid)

    await monitor_manager.connect(checkpoint_id, websocket)
    try:
        await websocket.send_json({"type": "state", **initial_state})
        # Read-only monitor: drain (and ignore) inbound frames until disconnect.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        monitor_manager.disconnect(checkpoint_id, websocket)
