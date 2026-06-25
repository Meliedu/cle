# backend/app/api/review.py
"""Instructor review + student follow-up API (Meli evidence loop, Phase 5).

Governing rule (Core §0.2 / §7): "AI drafts and suggests. Instructors review
meaning and action. Reviewed evidence becomes course memory and report output."

This router is the **evidence-conversion point** (Core §5.2): a draft
``LearningNote`` only becomes course memory once an instructor records a
``ReviewAction``. Reviewed notes may spawn ``FollowUpAction`` rows that surface
to the student as the doc's "Review Path".

Every endpoint returns the project ``APIResponse[T]`` envelope. The router
carries full paths; ``app.api.__init__`` mounts it under ``/api``.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import (
    get_db,
    get_owned_course,
    require_instructor,
    require_student,
)
from app.models import (
    FollowUpAction,
    InstructorAlert,
    LearningNote,
    ReviewAction,
)
from app.models.course import Course
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.evidence import (
    FollowUpActionResponse,
    LearningNoteResponse,
    NoteReviewStatus,
    ReviewActionCreate,
    ReviewActionResponse,
    ReviewQueueItem,
)

router = APIRouter(tags=["review"])

# Map a ReviewAction.action_type to the LearningNote.review_status it sets.
# Every value is a member of the learning_notes review_status CHECK constraint
# ('draft','queued','reviewed','edited','merged','split','archived').
_ACTION_TO_NOTE_STATUS: dict[str, str] = {
    "accept": "reviewed",
    "edit": "edited",
    "archive": "archived",
    "merge": "merged",
    "split": "split",
    "mark_resolved": "reviewed",
    "carry_forward": "reviewed",
    "assign_followup": "reviewed",
}

# FollowUpAction.action_type fallback when a review assigns a follow-up without
# an explicit inline spec (action_type == 'assign_followup' with no body.follow_up).
_DEFAULT_FOLLOW_UP_ACTION = "follow_up"


class ReviewActionResult(BaseModel):
    """Result of a review: the recorded action plus any follow-up it created.

    Composes the canonical evidence response models rather than redefining
    their field shapes (the follow_up id is reachable via ``follow_up.id``).
    """

    review_action: ReviewActionResponse
    follow_up: FollowUpActionResponse | None = None


# ---------------------------------------------------------------------------
# Instructor — review queue + learning notes
# ---------------------------------------------------------------------------
@router.get(
    "/courses/{course_id}/review-queue",
    response_model=APIResponse[list[ReviewQueueItem]],
)
async def get_review_queue(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[ReviewQueueItem]]:
    """Open Review Cases (InstructorAlert rows) + their linked draft notes.

    The InstructorAlert table is the Review-Case surface (CLE §5.4). Priority
    order matches the existing alert convention: severity then recency.
    """
    rows = (
        await db.execute(
            select(InstructorAlert, LearningNote)
            .outerjoin(
                LearningNote, LearningNote.id == InstructorAlert.linked_note_id
            )
            .where(
                InstructorAlert.course_id == course.id,
                InstructorAlert.status == "open",
            )
            .order_by(
                InstructorAlert.severity.desc(),
                InstructorAlert.created_at.desc(),
            )
            .limit(limit)
        )
    ).all()

    items: list[ReviewQueueItem] = []
    for alert, note in rows:
        item = ReviewQueueItem.model_validate(alert)
        if note is not None:
            item = item.model_copy(
                update={"linked_note": LearningNoteResponse.model_validate(note)}
            )
        items.append(item)

    return APIResponse(success=True, data=items)


@router.get(
    "/courses/{course_id}/learning-notes",
    response_model=APIResponse[list[LearningNoteResponse]],
)
async def list_learning_notes(
    review_status: NoteReviewStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[LearningNoteResponse]]:
    """Learning notes for an owned course.

    Filters by ``review_status`` when supplied; otherwise excludes archived
    notes so the default view shows live evidence only.
    """
    stmt = select(LearningNote).where(LearningNote.course_id == course.id)
    if review_status is not None:
        stmt = stmt.where(LearningNote.review_status == review_status)
    else:
        stmt = stmt.where(LearningNote.review_status != "archived")
    stmt = stmt.order_by(LearningNote.created_at.desc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    return APIResponse(
        success=True,
        data=[LearningNoteResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/learning-notes/{note_id}/review",
    response_model=APIResponse[ReviewActionResult],
)
async def review_learning_note(
    note_id: uuid.UUID,
    body: ReviewActionCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_instructor),
) -> APIResponse[ReviewActionResult]:
    """Evidence-conversion point (Core §5.2).

    Records an immutable ``ReviewAction``, flips the note's ``review_status``,
    and — when the action assigns a follow-up — creates a ``FollowUpAction``
    that the student will see on their Review Path.
    """
    note = (
        await db.execute(select(LearningNote).where(LearningNote.id == note_id))
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="Learning note not found")

    # Ownership: the note's course must belong to the acting instructor. 404
    # (not 403) so we don't leak the existence of notes in other courses.
    owned = (
        await db.execute(
            select(Course).where(
                Course.id == note.course_id,
                Course.instructor_id == actor.id,
                Course.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if owned is None:
        raise HTTPException(status_code=404, detail="Learning note not found")

    prior_status = note.review_status
    new_status = _ACTION_TO_NOTE_STATUS.get(body.action_type, prior_status)

    # 'edit' with edit_text rewrites the draft interpretation.
    if body.action_type == "edit" and body.edit_text is not None:
        note.draft_interpretation = body.edit_text

    # report_eligibility: apply the requested value (if any) and record whether
    # it actually changed from the prior state.
    prior_eligibility = note.report_eligibility
    if body.report_eligibility is not None:
        note.report_eligibility = body.report_eligibility
    report_eligibility_change = (
        body.report_eligibility is not None
        and body.report_eligibility != prior_eligibility
    )

    now = datetime.now(timezone.utc)
    note.review_status = new_status
    note.updated_at = now

    review_action = ReviewAction(
        learning_note_id=note.id,
        reviewer_id=actor.id,
        reviewer_role=actor.role,
        action_type=body.action_type,
        prior_status=prior_status,
        new_status=new_status,
        edit_text=body.edit_text,
        report_eligibility_change=report_eligibility_change,
    )
    db.add(review_action)

    # Create a follow-up when the review explicitly assigns one, either via the
    # 'assign_followup' action or by attaching an inline follow-up spec.
    follow_up: FollowUpAction | None = None
    spec = body.follow_up
    if spec is not None or body.action_type == "assign_followup":
        target_user_id = (spec.user_id if spec else None) or note.user_id
        if target_user_id is None:
            # A cohort note with no explicit target cannot be assigned a
            # student-facing follow-up.
            raise HTTPException(
                status_code=400,
                detail="Follow-up requires a target user (note has no student)",
            )
        follow_up = FollowUpAction(
            learning_note_id=note.id,
            course_id=note.course_id,
            user_id=target_user_id,
            action_type=(
                spec.action_type if spec else _DEFAULT_FOLLOW_UP_ACTION
            ),
            target_kind=spec.target_kind if spec else None,
            target_id=spec.target_id if spec else None,
            due_at=spec.due_at if spec else None,
            assignment_status="assigned",
            assigned_by=actor.id,
        )
        db.add(follow_up)

    await db.commit()
    await db.refresh(review_action)
    if follow_up is not None:
        await db.refresh(follow_up)

    result = ReviewActionResult(
        review_action=ReviewActionResponse.model_validate(review_action),
        follow_up=(
            FollowUpActionResponse.model_validate(follow_up)
            if follow_up is not None
            else None
        ),
    )
    return APIResponse(success=True, data=result)


# ---------------------------------------------------------------------------
# Student — follow-up Review Path
# ---------------------------------------------------------------------------
@router.get(
    "/users/me/courses/{course_id}/follow-ups",
    response_model=APIResponse[list[FollowUpActionResponse]],
)
async def list_my_follow_ups(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student),
) -> APIResponse[list[FollowUpActionResponse]]:
    """The caller's active follow-ups in a course (the doc's Review Path).

    Only assigned/viewed rows surface; completion is auto-detected later by the
    mastery outcome-closure when the next attempt lands.
    """
    await verify_enrollment(db, course_id, student.id)

    rows = (
        await db.execute(
            select(FollowUpAction)
            .where(
                FollowUpAction.user_id == student.id,
                FollowUpAction.course_id == course_id,
                FollowUpAction.assignment_status.in_(("assigned", "viewed")),
            )
            .order_by(FollowUpAction.created_at.desc())
        )
    ).scalars().all()

    return APIResponse(
        success=True,
        data=[FollowUpActionResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/follow-ups/{follow_up_id}/viewed",
    response_model=APIResponse[FollowUpActionResponse],
)
async def mark_follow_up_viewed(
    follow_up_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student),
) -> APIResponse[FollowUpActionResponse]:
    """Mark an assigned follow-up as viewed (idempotent).

    Completion is NOT recorded here — the mastery outcome-closure detects it
    automatically when the student's next attempt produces a Learning Event.
    """
    row = (
        await db.execute(
            select(FollowUpAction).where(FollowUpAction.id == follow_up_id)
        )
    ).scalar_one_or_none()
    # 404 (not 403) when the row belongs to another student, masking existence.
    if row is None or row.user_id != student.id:
        raise HTTPException(status_code=404, detail="Follow-up not found")

    if row.assignment_status == "assigned":
        row.assignment_status = "viewed"
        await db.commit()
        await db.refresh(row)

    return APIResponse(
        success=True, data=FollowUpActionResponse.model_validate(row)
    )
