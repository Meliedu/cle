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
    OutcomeCheck,
    ReviewAction,
)
from app.models.course import Course, Enrollment
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.evidence import (
    FollowUpActionResponse,
    FollowUpDetailResponse,
    FollowUpRevisitLink,
    LearningNoteResponse,
    NoteReviewStatus,
    ReviewActionCreate,
    ReviewActionResponse,
    ReviewQueueItem,
)
from app.services.work_items import upsert_progress, upsert_work_item

router = APIRouter(tags=["review"])

# Follow-up statuses that still occupy a student's Review Path — a re-review
# reuses one of these rather than spawning a duplicate follow-up (Decision 3).
_ACTIVE_FOLLOW_UP_STATUSES = ("suggested", "assigned", "viewed")

# Cap the checklist row title at the work_items.title column width (255).
_FOLLOW_UP_TITLE_MAX = 255

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

# LearningNote.review_status values that mean an instructor has reviewed the
# note, so its content may be shown to the student (Core §0.2 / Decision 6).
# The complement ('draft','queued') is AI-drafted and never surfaced; 'archived'
# is a removed note and also withheld.
_REVIEWED_NOTE_STATUSES = frozenset({"reviewed", "edited", "merged", "split"})


def _follow_up_title(note: LearningNote, follow_up: FollowUpAction) -> str:
    """A short, human title for the follow-up's checklist row.

    Prefers the note's ``observed_signal`` (the concrete thing the student will
    recognise), falling back to the follow-up's ``action_type`` label. Truncated
    to the ``work_items.title`` column width.
    """
    label = (note.observed_signal or "").strip() or follow_up.action_type
    return f"Follow-up: {label}"[:_FOLLOW_UP_TITLE_MAX]


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
        # Access-control (MEDIUM): when the reviewer supplies an explicit target
        # via `spec.user_id`, it must be an ACTIVE student of the note's course.
        # Otherwise an instructor could mint a follow-up (+ work_item + progress
        # row) for an ARBITRARY user, who could then read the reviewed note's
        # content via GET /users/me/follow-ups/{id}. A non-enrolled TARGET is a
        # bad request on the instructor's action (400), not a 403 on the actor.
        # This check runs BEFORE any follow-up/work_item write, so a rejected
        # target writes nothing. The note.user_id fallback is system-derived
        # (set at note-drafting from a Learning Event), not actor-controlled.
        if spec is not None and spec.user_id is not None:
            enrolled = (
                await db.execute(
                    select(Enrollment.id).where(
                        Enrollment.course_id == note.course_id,
                        Enrollment.user_id == target_user_id,
                        Enrollment.status == "active",
                    )
                )
            ).first()
            if enrolled is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Follow-up target is not an active student of this course"
                    ),
                )
        # Guarded upstream (Decision 3): reuse an existing ACTIVE follow-up for
        # this (note, student) rather than spawning a duplicate — so a re-review
        # never creates a second follow-up (and thus a second work_item).
        follow_up = (
            await db.execute(
                select(FollowUpAction).where(
                    FollowUpAction.learning_note_id == note.id,
                    FollowUpAction.user_id == target_user_id,
                    FollowUpAction.assignment_status.in_(
                        _ACTIVE_FOLLOW_UP_STATUSES
                    ),
                )
            )
        ).scalars().first()
        if follow_up is None:
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

        # Transactional checklist-spine write (P6 B1, Decision 3): a reviewed
        # follow-up becomes a `follow_up` work_item + a per-student progress row,
        # riding this endpoint's single commit so the follow-up, its ReviewAction,
        # the work_item and the progress row all persist (or roll back) atomically.
        # Idempotent on the (course_id, source_kind='follow_up', source_id) unique
        # index — the reuse guard above keeps source_id stable across re-reviews.
        # Mirrors checkpoints.py::publish_checkpoint's publish→work_item seam.
        await db.flush()  # materialize follow_up.id before the upsert
        title = _follow_up_title(note, follow_up)
        work_item = await upsert_work_item(
            db,
            course_id=follow_up.course_id,
            source_kind="follow_up",
            source_id=follow_up.id,
            title=title,
            required=True,
            score_bearing=False,
            due_at=follow_up.due_at,
            close_at=follow_up.due_at,
            created_by=actor.id,
        )
        # Keep the checklist row's schedule/title in sync on a re-review (choice
        # b, mirroring publish): on_conflict_do_nothing returns the existing row
        # unchanged, so re-apply the current follow-up's timing/title.
        if work_item.due_at != follow_up.due_at:
            work_item.due_at = follow_up.due_at
        if work_item.close_at != follow_up.due_at:
            work_item.close_at = follow_up.due_at
        if work_item.title != title:
            work_item.title = title
        await upsert_progress(
            db,
            work_item_id=work_item.id,
            user_id=follow_up.user_id,
            status="follow_up_assigned",
        )

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


@router.get(
    "/users/me/follow-ups/{follow_up_id}",
    response_model=APIResponse[FollowUpDetailResponse],
)
async def get_follow_up_detail(
    follow_up_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student),
) -> APIResponse[FollowUpDetailResponse]:
    """One follow-up's action detail for its owner (the doc's Review Path item).

    Owner-scoped by ``user_id`` — another student's row is masked as 404, never
    403 (no existence leak). Merges the follow-up with its linked ``LearningNote``'s
    **reviewed** fields ONLY (``observed_signal`` / ``draft_interpretation`` /
    ``limitation_note``); a ``draft``/``queued`` note's AI content is withheld
    (Core §0.2, Decision 6). Surfaces the linked ``OutcomeCheck.status`` (the "did
    it move" state) and — for a ``checkpoint`` target — the P3 revisit link. A
    ``suggested`` follow-up (not yet instructor-assigned) returns the designed
    waiting-for-feedback shape with no action content.
    """
    row = (
        await db.execute(
            select(FollowUpAction).where(FollowUpAction.id == follow_up_id)
        )
    ).scalar_one_or_none()
    # 404 (not 403) when the row belongs to another student, masking existence.
    if row is None or row.user_id != student.id:
        raise HTTPException(status_code=404, detail="Follow-up not found")

    # Access-control (LOW-1): gate the reviewed-note content read on an ACTIVE
    # enrollment — matching get_signal / list_my_follow_ups. A dropped/rejected/
    # pending student must not retain read access to their own follow-up's
    # reviewed note content. verify_enrollment raises 403 (owner already proven).
    await verify_enrollment(db, row.course_id, student.id)

    note: LearningNote | None = None
    if row.learning_note_id is not None:
        note = (
            await db.execute(
                select(LearningNote).where(LearningNote.id == row.learning_note_id)
            )
        ).scalar_one_or_none()

    note_reviewed = (
        note is not None and note.review_status in _REVIEWED_NOTE_STATUSES
    )
    # Waiting-for-feedback shape: a not-yet-assigned (suggested) follow-up, or one
    # whose note has not been reviewed, carries no action content (Decision 6).
    waiting = row.assignment_status == "suggested" or not note_reviewed

    outcome_status = (
        await db.execute(
            select(OutcomeCheck.status).where(
                OutcomeCheck.follow_up_action_id == row.id
            )
        )
    ).scalar_one_or_none()

    revisit: FollowUpRevisitLink | None = None
    if not waiting and row.target_kind == "checkpoint" and row.target_id is not None:
        revisit = FollowUpRevisitLink(
            checkpoint_id=row.target_id,
            revisit_path=f"/api/checkpoints/{row.target_id}/revisit-response",
        )

    detail = FollowUpDetailResponse(
        id=row.id,
        course_id=row.course_id,
        learning_note_id=row.learning_note_id,
        action_type=row.action_type,
        target_kind=row.target_kind,
        target_id=row.target_id,
        assignment_status=row.assignment_status,
        due_at=row.due_at,
        created_at=row.created_at,
        waiting_for_review=waiting,
        observed_signal=note.observed_signal if note_reviewed else None,
        draft_interpretation=(
            note.draft_interpretation if note_reviewed else None
        ),
        limitation_note=note.limitation_note if note_reviewed else None,
        outcome_status=outcome_status,
        revisit=revisit,
    )
    return APIResponse(success=True, data=detail)


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

    # Defense-in-depth (matches get_follow_up_detail / get_signal): a non-active
    # (dropped/rejected/pending) owner loses access to their OWN follow-up. 403
    # only ever fires for the caller's own row, so it leaks nothing.
    await verify_enrollment(db, row.course_id, student.id)

    if row.assignment_status == "assigned":
        row.assignment_status = "viewed"
        await db.commit()
        await db.refresh(row)

    return APIResponse(
        success=True, data=FollowUpActionResponse.model_validate(row)
    )
