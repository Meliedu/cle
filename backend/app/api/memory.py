"""Course-memory router (P7 Task B8).

The teacher surface over ``course_record_items`` — the durable, reviewed course
memory (spec §4.10, Decision 5). Two routers are exported:

- ``router`` under ``/courses/{course_id}/memory`` — course-scoped: the memory
  list, guarded by ``get_owned_course``.
- ``item_router`` under ``/memory`` — per-item: detail + decide, guarded by
  ``_get_owned_item`` (resolve item → its course → owner check, 404 on mismatch
  so item/course existence is never leaked — mirrors ``reports.py``).

``POST /memory/{id}/decide`` records the instructor decision
(``keep|revise|reject|carry_forward``): it sets ``decision`` / ``decided_by`` /
``decided_at``, syncs the ``carry_forward`` bool (true iff decision is
``carry_forward``), appends an append-only ``audit_events`` row
(``memory.decide`` / ``course_record_item``) ALWAYS, and appends a
``review_action`` ONLY when the item is note-linked (``learning_note_id`` present
— its FK is NOT NULL, so a null-note item can only be audited via
``audit_events``; Decision 5). ``reject`` is an audited tombstone (no hard
delete — the table has no soft-delete column).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_course, require_instructor
from app.database import get_db
from app.models.course import Course
from app.models.evidence import CourseRecordItem, ReviewAction
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.memory import (
    MemoryDecideRequest,
    MemoryDecisionCounts,
    MemoryItemResponse,
    MemorySummaryResponse,
    NextTermSuggestionResponse,
)

router = APIRouter(prefix="/courses/{course_id}/memory", tags=["memory"])
# Per-item routes are NOT nested under a course — a record-item id is globally
# unique, so ownership is resolved from the item's own course (mirrors reports).
item_router = APIRouter(prefix="/memory", tags=["memory"])

# Maps the memory decision → the note-scoped ReviewAction.action_type (whose
# CHECK already includes these). Only used when the item is note-linked.
_DECISION_TO_ACTION_TYPE = {
    "keep": "accept",
    "revise": "edit",
    "reject": "archive",
    "carry_forward": "carry_forward",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _derive_kind(item: CourseRecordItem) -> str:
    """Label the item by which summary JSONBs are populated (priority order).

    outcome > action > relationship > general. An outcome-closure item (the
    common case, written by ``mastery.py::_close_follow_ups``) carries only
    ``outcome_summary`` → ``"outcome"``.
    """
    if item.outcome_summary:
        return "outcome"
    if item.action_summary:
        return "action"
    if item.relationship_summary:
        return "relationship"
    return "general"


def _to_response(item: CourseRecordItem) -> MemoryItemResponse:
    return MemoryItemResponse(
        id=item.id,
        course_id=item.course_id,
        learning_note_id=item.learning_note_id,
        kind=_derive_kind(item),
        relationship_summary=item.relationship_summary,
        action_summary=item.action_summary,
        outcome_summary=item.outcome_summary,
        instructor_comment=item.instructor_comment,
        carry_forward=item.carry_forward,
        decision=item.decision,
        decided_by=item.decided_by,
        decided_at=item.decided_at,
        report_history=item.report_history,
        created_at=item.created_at,
    )


async def _get_owned_item(
    item_id: uuid.UUID, user: User, db: AsyncSession
) -> CourseRecordItem:
    """Resolve a record item whose course the authenticated instructor owns.

    404 (never 403) on a missing item OR a course the caller doesn't own, so
    item/course existence is never leaked — mirrors ``reports.py::_get_owned_report``.
    """
    item = await db.get(CourseRecordItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    course = await db.get(Course, item.course_id)
    if (
        course is None
        or course.deleted_at is not None
        or course.instructor_id != user.id
    ):
        raise HTTPException(status_code=404, detail="Memory item not found")
    return item


@router.get("", response_model=APIResponse[list[MemoryItemResponse]])
async def list_memory(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[MemoryItemResponse]]:
    """The course's memory record items, newest first (owner-guarded).

    Each item's ``kind`` is derived from its populated summary JSONBs. Backed by
    the ``(course_id, created_at DESC)`` index.
    """
    stmt = (
        select(CourseRecordItem)
        .where(CourseRecordItem.course_id == course.id)
        .order_by(CourseRecordItem.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return APIResponse(success=True, data=[_to_response(r) for r in rows])


@router.get(
    "/next-term-suggestions",
    response_model=APIResponse[list[NextTermSuggestionResponse]],
)
async def next_term_suggestions(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[NextTermSuggestionResponse]]:
    """Carry-forward memory from PRIOR-term courses of the same lineage (T023).

    Lineage = the SAME ``courses.code`` + the SAME ``instructor_id`` on a
    DIFFERENT (prior) course — NEVER matched on student identity (Decision 6). A
    course with no ``code`` has no lineage → empty. Only ``decision='carry_forward'``
    items are suggested; undecided / ``reject`` / ``keep`` are excluded.
    """
    if not course.code:
        return APIResponse(success=True, data=[])

    stmt = (
        select(CourseRecordItem, Course)
        .join(Course, Course.id == CourseRecordItem.course_id)
        .where(
            Course.code == course.code,
            Course.instructor_id == course.instructor_id,
            Course.id != course.id,
            Course.deleted_at.is_(None),
            CourseRecordItem.decision == "carry_forward",
        )
        .order_by(CourseRecordItem.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    data = [
        NextTermSuggestionResponse(
            **_to_response(item).model_dump(),
            source_course_id=src.id,
            source_course_code=src.code,
            source_course_name=src.name,
        )
        for item, src in rows
    ]
    return APIResponse(success=True, data=data)


@router.get("/summary", response_model=APIResponse[MemorySummaryResponse])
async def memory_summary(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[MemorySummaryResponse]:
    """Counts-by-decision + the carry-forward roster for the teacher overview (T036)."""
    rows = (
        await db.execute(
            select(CourseRecordItem)
            .where(CourseRecordItem.course_id == course.id)
            .order_by(CourseRecordItem.created_at.desc())
        )
    ).scalars().all()

    counts = MemoryDecisionCounts()
    for item in rows:
        key = item.decision or "undecided"
        setattr(counts, key, getattr(counts, key) + 1)

    roster = [
        _to_response(item) for item in rows if item.decision == "carry_forward"
    ]
    return APIResponse(
        success=True,
        data=MemorySummaryResponse(
            total=len(rows), counts=counts, carry_forward_roster=roster
        ),
    )


@item_router.get("/{item_id}", response_model=APIResponse[MemoryItemResponse])
async def get_memory_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[MemoryItemResponse]:
    """Memory item detail (owner-guarded via its course)."""
    item = await _get_owned_item(item_id, user, db)
    return APIResponse(success=True, data=_to_response(item))


@item_router.post(
    "/{item_id}/decide", response_model=APIResponse[MemoryItemResponse]
)
async def decide_memory_item(
    item_id: uuid.UUID,
    body: MemoryDecideRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[MemoryItemResponse]:
    """Record the instructor decision on a memory item (Decision 5).

    Sets ``decision`` / ``decided_by`` / ``decided_at`` and syncs
    ``carry_forward`` (true iff decision is ``carry_forward``). ALWAYS appends an
    append-only ``audit_events`` row (``memory.decide``); ADDITIONALLY appends a
    ``review_action`` ONLY when the item is note-linked (``learning_note_id``
    present). ``reject`` is an audited tombstone (no hard delete). An out-of-enum
    decision is rejected with 422 before this handler runs; a non-owner → 404.
    """
    from app.services.audit import record_audit_event

    item = await _get_owned_item(item_id, user, db)
    decision = body.decision

    item.decision = decision
    item.decided_by = user.id
    item.decided_at = _utcnow()
    item.carry_forward = decision == "carry_forward"

    await record_audit_event(
        db,
        course_id=item.course_id,
        actor_id=user.id,
        event_type="memory.decide",
        target_kind="course_record_item",
        target_id=item.id,
        metadata={"decision": decision},
    )

    # ReviewAction.learning_note_id is NOT NULL — only appendable when the item
    # is note-linked. A null-note memory decision is audited via audit_events
    # alone (Decision 5).
    if item.learning_note_id is not None:
        db.add(
            ReviewAction(
                learning_note_id=item.learning_note_id,
                reviewer_id=user.id,
                reviewer_role=user.role,
                action_type=_DECISION_TO_ACTION_TYPE[decision],
            )
        )

    await db.commit()
    await db.refresh(item)
    return APIResponse(success=True, data=_to_response(item))
