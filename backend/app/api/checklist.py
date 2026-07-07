"""Checklist router (P4 B6): student read + next-action + teacher manager.

The course checklist spine (spec §4.6) is exposed through two audiences:

* STUDENT (enrollment-scoped via ``verify_enrollment`` — active-only, 403
  otherwise):
  - ``GET /courses/{id}/checklist`` — the course's non-deleted ``work_items``
    merged with the CALLER'S OWN ``work_item_progress``, ordered by ``due_at``
    then ``visible_from``. A pre-backfill checkpoint item with no progress row
    derives its status from ``checkpoint_responses`` (Decision 4) so history
    isn't blank; anything else with no progress is ``pending``.
  - ``GET /courses/{id}/next-action`` — the single next ``pending``/
    ``in_progress`` item by ``due_at`` (Decision 7), or ``null``.

* TEACHER (owner-guarded — 404 on a non-owner, never 403, so course existence
  isn't leaked):
  - ``GET /courses/{id}/work-items`` — the raw work_items (NO per-student
    progress).
  - ``POST /courses/{id}/work-items`` — a manual add.
  - ``PATCH /work-items/{id}`` — reorder / required / title edits.
  - ``DELETE /work-items/{id}`` — soft-remove.

Two routers are exported (mirrors ``api/attendance.py``): ``course_router`` under
``/courses/{course_id}`` (student reads + teacher list/create) and ``item_router``
under ``/work-items`` (teacher patch/delete by item id).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment as _verify_enrollment
from app.api.deps import get_owned_course, require_instructor, require_student
from app.database import get_db
from app.models.checkpoint import CheckpointCard, CheckpointResponse
from app.models.course import Course
from app.models.user import User
from app.models.work_item import WorkItem, WorkItemProgress
from app.schemas.common import APIResponse
from app.schemas.work_item import (
    ChecklistItem,
    WorkItemCreate,
    WorkItemResponse,
    WorkItemUpdate,
)
from app.services.checkpoint_responses import _derive_progress_status
from app.services.work_items import remove_work_item, upsert_work_item

course_router = APIRouter(prefix="/courses/{course_id}", tags=["checklist"])
item_router = APIRouter(prefix="/work-items", tags=["checklist"])

# The default per-item status when the caller has no progress row and there is
# nothing to derive one from.
_DEFAULT_STATUS = "pending"

# Statuses that still need the student's attention — the next-action pool.
_ACTIONABLE_STATUSES = frozenset({"pending", "in_progress"})


async def _owned_work_item(
    work_item_id: uuid.UUID, user: User, db: AsyncSession
) -> WorkItem:
    """Resolve a work_item the authenticated instructor owns (404 otherwise).

    Mirrors ``_owned_checkpoint`` / ``_owned_meeting``: a non-owner (or a
    missing / soft-deleted item / course) is a 404 so course existence is never
    leaked to an unauthorized caller.
    """
    wi = await db.get(WorkItem, work_item_id)
    if wi is None or wi.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Work item not found")
    course = await db.get(Course, wi.course_id)
    if (
        course is None
        or course.deleted_at is not None
        or course.instructor_id != user.id
    ):
        raise HTTPException(status_code=404, detail="Work item not found")
    return wi


async def _fallback_statuses(
    db: AsyncSession,
    *,
    checkpoint_ids: list[uuid.UUID],
    user_id: uuid.UUID,
) -> dict[uuid.UUID, str]:
    """Derive per-checkpoint status from the student's ``checkpoint_responses``.

    Decision 4: a checkpoint work_item that predates B5's progress writes has no
    ``work_item_progress`` row, so its checklist status is derived from the
    student's own responses — mirroring B5's ``_derive_progress_status`` so a
    backfilled item reads the same as a freshly-answered one.

    Returns a ``{checkpoint_id: status}`` map for checkpoints the student has
    responded to; checkpoints with no response are omitted (the caller defaults
    them to ``pending``).
    """
    if not checkpoint_ids:
        return {}

    # Join LIVE (non-deleted) cards only (P7 B11, Decision 9.2): keep the on-time
    # numerator and the live-card denominator consistent so a response to a
    # since-soft-deleted card can't spuriously derive ``completed``.
    responses = (
        await db.execute(
            select(CheckpointResponse.checkpoint_id, CheckpointResponse.status)
            .join(CheckpointCard, CheckpointCard.id == CheckpointResponse.card_id)
            .where(
                CheckpointResponse.checkpoint_id.in_(checkpoint_ids),
                CheckpointResponse.user_id == user_id,
                CheckpointCard.deleted_at.is_(None),
            )
        )
    ).all()
    if not responses:
        return {}

    on_time_by_cp: dict[uuid.UUID, int] = {}
    any_late_by_cp: dict[uuid.UUID, bool] = {}
    for cp_id, status_value in responses:
        if status_value == "late":
            any_late_by_cp[cp_id] = True
        else:
            on_time_by_cp[cp_id] = on_time_by_cp.get(cp_id, 0) + 1

    # Live (non-removed) card counts — the "answered all" denominator.
    live_counts = (
        await db.execute(
            select(CheckpointCard.checkpoint_id, func.count())
            .where(
                CheckpointCard.checkpoint_id.in_(checkpoint_ids),
                CheckpointCard.deleted_at.is_(None),
            )
            .group_by(CheckpointCard.checkpoint_id)
        )
    ).all()
    live_count_by_cp = {cp_id: count for cp_id, count in live_counts}

    responded_cp_ids = set(on_time_by_cp) | set(any_late_by_cp)
    derived: dict[uuid.UUID, str] = {}
    for cp_id in responded_cp_ids:
        derived[cp_id] = _derive_progress_status(
            row_status="late" if any_late_by_cp.get(cp_id) else "on_time",
            on_time_count=on_time_by_cp.get(cp_id, 0),
            live_card_count=live_count_by_cp.get(cp_id, 0),
        )
    return derived


async def _build_checklist(
    db: AsyncSession, *, course_id: uuid.UUID, user_id: uuid.UUID
) -> list[ChecklistItem]:
    """Merge the course's work_items with the caller's own progress.

    Ordered by ``due_at`` then ``visible_from`` (Postgres NULLS LAST on ASC, so
    dateless items sort to the end). Status precedence: the caller's
    ``work_item_progress`` row → the ``checkpoint_responses`` fallback (Decision
    4) → ``pending``.
    """
    # ``visible_from`` release gate (P7 B11, Decision 9.1): an item with a FUTURE
    # ``visible_from`` is not yet released, so it is hidden from the checklist; a
    # past or NULL ``visible_from`` shows (spec §4.6 release semantics).
    now = datetime.now(timezone.utc)
    items = list(
        (
            await db.execute(
                select(WorkItem)
                .where(
                    WorkItem.course_id == course_id,
                    WorkItem.deleted_at.is_(None),
                    or_(
                        WorkItem.visible_from.is_(None),
                        WorkItem.visible_from <= now,
                    ),
                )
                .order_by(WorkItem.due_at, WorkItem.visible_from)
            )
        ).scalars().all()
    )
    if not items:
        return []

    item_ids = [wi.id for wi in items]
    progress_by_item = {
        row.work_item_id: row.status
        for row in (
            await db.execute(
                select(WorkItemProgress).where(
                    WorkItemProgress.work_item_id.in_(item_ids),
                    WorkItemProgress.user_id == user_id,
                )
            )
        ).scalars().all()
    }

    # Fallback only for checkpoint items with no progress row (pre-backfill).
    fallback_cp_ids = [
        wi.source_id
        for wi in items
        if wi.source_kind == "checkpoint" and wi.id not in progress_by_item
    ]
    fallback_by_cp = await _fallback_statuses(
        db, checkpoint_ids=fallback_cp_ids, user_id=user_id
    )

    result: list[ChecklistItem] = []
    for wi in items:
        status_value = progress_by_item.get(wi.id)
        if status_value is None and wi.source_kind == "checkpoint":
            status_value = fallback_by_cp.get(wi.source_id)
        if status_value is None:
            status_value = _DEFAULT_STATUS
        result.append(
            ChecklistItem(
                id=wi.id,
                course_id=wi.course_id,
                source_kind=wi.source_kind,  # type: ignore[arg-type]
                source_id=wi.source_id,
                title=wi.title,
                required=wi.required,
                score_bearing=wi.score_bearing,
                due_at=wi.due_at,
                close_at=wi.close_at,
                visible_from=wi.visible_from,
                status=status_value,  # type: ignore[arg-type]
            )
        )
    return result


# ----- student reads (enrollment-scoped) -----


@course_router.get("/checklist", response_model=APIResponse[list[ChecklistItem]])
async def get_checklist(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[list[ChecklistItem]]:
    """The student's own checklist for a course (S024/S025).

    Enrollment-scoped (403 for a non-enrolled / pending / rejected student).
    """
    await _verify_enrollment(db, course_id, user.id)
    items = await _build_checklist(db, course_id=course_id, user_id=user.id)
    return APIResponse(success=True, data=items)


@course_router.get("/next-action", response_model=APIResponse[ChecklistItem])
async def get_next_action(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[ChecklistItem | None]:
    """The single next ``pending``/``in_progress`` item by ``due_at`` (Decision 7).

    Reads the SAME spine as the checklist (already ordered by ``due_at`` then
    ``visible_from``); the first still-actionable item is the next action.
    ``data`` is ``null`` when nothing is outstanding.
    """
    await _verify_enrollment(db, course_id, user.id)
    items = await _build_checklist(db, course_id=course_id, user_id=user.id)
    nxt = next(
        (item for item in items if item.status in _ACTIONABLE_STATUSES), None
    )
    return APIResponse(success=True, data=nxt)


# ----- teacher manager (owner-guarded) -----


@course_router.get("/work-items", response_model=APIResponse[list[WorkItemResponse]])
async def list_work_items(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[WorkItemResponse]]:
    """The course's non-deleted work_items (owner-guarded; NO per-student progress)."""
    rows = (
        await db.execute(
            select(WorkItem)
            .where(
                WorkItem.course_id == course.id,
                WorkItem.deleted_at.is_(None),
            )
            .order_by(WorkItem.due_at, WorkItem.visible_from)
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[WorkItemResponse.model_validate(wi) for wi in rows],
    )


@course_router.post(
    "/work-items",
    response_model=APIResponse[WorkItemResponse],
    status_code=201,
)
async def create_work_item(
    body: WorkItemCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
    user: User = Depends(require_instructor),
) -> APIResponse[WorkItemResponse]:
    """Manually add a work_item to a course (owner-guarded).

    A manual item has no backing artifact, so ``source_id`` is server-generated
    (a fresh UUID never collides on the ``(course, source_kind, source_id)``
    unique index). Reuses the idempotent ``upsert_work_item`` service.
    """
    wi = await upsert_work_item(
        db,
        course_id=course.id,
        source_kind=body.source_kind,
        source_id=uuid.uuid4(),
        title=body.title,
        required=body.required,
        score_bearing=body.score_bearing,
        due_at=body.due_at,
        close_at=body.close_at,
        created_by=user.id,
    )
    if body.visible_from is not None:
        wi.visible_from = body.visible_from
    await db.commit()
    await db.refresh(wi)
    return APIResponse(success=True, data=WorkItemResponse.model_validate(wi))


@item_router.patch(
    "/{work_item_id}", response_model=APIResponse[WorkItemResponse]
)
async def update_work_item(
    work_item_id: uuid.UUID,
    body: WorkItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[WorkItemResponse]:
    """Edit a work_item's title / required / score_bearing / timing (owner-guarded).

    Only supplied fields are applied (``exclude_unset``), so passing an explicit
    ``null`` clears a timestamp while omitting a field leaves it untouched.
    """
    wi = await _owned_work_item(work_item_id, user, db)
    fields = body.model_dump(exclude_unset=True)
    for field in (
        "title", "required", "score_bearing", "due_at", "close_at", "visible_from"
    ):
        if field in fields:
            setattr(wi, field, fields[field])
    await db.commit()
    await db.refresh(wi)
    return APIResponse(success=True, data=WorkItemResponse.model_validate(wi))


@item_router.delete(
    "/{work_item_id}", response_model=APIResponse[None]
)
async def delete_work_item(
    work_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[None]:
    """Soft-remove a work_item (owner-guarded)."""
    wi = await _owned_work_item(work_item_id, user, db)
    await remove_work_item(db, wi)
    await db.commit()
    return APIResponse(success=True, data=None)
