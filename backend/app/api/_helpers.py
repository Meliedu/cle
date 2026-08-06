import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course, Enrollment
from app.models.task import Task


async def verify_enrollment(
    db: AsyncSession,
    course_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Require an *active* enrollment in a non-soft-deleted course.

    Joins to ``Course`` so soft-deleted courses fail verification in a single
    query, avoiding the stale-course / stale-enrollment gap that would appear
    if we checked enrollment alone.

    The ``status == "active"`` clause is load-bearing security: P2 join-approval
    creates ``status='pending'`` rows for code+approval courses (and rejected
    students keep a ``status='rejected'`` row). Without this filter a pending or
    rejected student would clear the gate and reach the entire student surface
    (checkpoint responses, quizzes, flashcards, mastery writes, …) for a course
    the teacher never admitted them to.
    """
    result = await db.execute(
        select(Enrollment)
        .join(Course, Course.id == Enrollment.course_id)
        .where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
            Enrollment.status == "active",
            Course.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enrolled in this course",
        )


async def verify_instructor_enrollment(
    db: AsyncSession,
    course_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Require instructor standing *in this specific course*.

    Passes when the caller either owns the course (``courses.instructor_id``)
    or holds an active instructor-role enrollment in it. Raises 403 otherwise,
    or if the course has been soft-deleted.

    Use this, not ``verify_enrollment``, for anything instructor-only.
    ``require_instructor`` alone only proves the caller is HKUST staff
    *somewhere* (``User.role`` is derived from the email domain), and
    ``verify_enrollment`` accepts an enrollment of ANY role. Since an enroll
    code is shared with a whole class it is no secret from other staff, so
    those two together let any ``@ust.hk`` account self-enrol into a course it
    does not teach and clear both gates.

    Ownership is accepted alongside the enrollment because the course owner is
    by definition its instructor. Requiring the enrollment row alone would lock
    an owner out of their own course on any historical row where that row is
    missing, and the owner check is free here (the ``Course`` join already
    exists for the soft-delete filter).
    """
    result = await db.execute(
        select(Course.id)
        .outerjoin(
            Enrollment,
            (Enrollment.course_id == Course.id)
            & (Enrollment.user_id == user_id)
            & (Enrollment.role == "instructor")
            # Load-bearing: a code+approval course can leave an instructor-role
            # enrollment in `pending`/`rejected`; without this an un-admitted
            # instructor would clear the gate. Mirrors verify_enrollment.
            & (Enrollment.status == "active"),
        )
        .where(
            Course.id == course_id,
            Course.deleted_at.is_(None),
            (Course.instructor_id == user_id) | (Enrollment.id.isnot(None)),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not an instructor for this course",
        )


async def enqueue_note_drafting(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
) -> None:
    """Enqueue a ``draft_learning_notes`` task for a course, deduped.

    Note drafting is batch/periodic work — one pending task per course is
    sufficient. If a ``draft_learning_notes`` task for this course is already
    pending or running, skip the enqueue so a burst of attempts doesn't pile
    up redundant draft passes. ``Task.payload`` is JSON, so the course filter
    uses ``->>`` text extraction. The Task row is added to the caller's
    session; the caller commits.
    """
    existing = (
        await db.execute(
            select(Task.id).where(
                Task.task_type == "draft_learning_notes",
                Task.status.in_(("pending", "running")),
                Task.payload.op("->>")("course_id") == str(course_id),
            )
        )
    ).first()
    if existing is not None:
        return
    db.add(
        Task(
            task_type="draft_learning_notes",
            payload={"course_id": str(course_id)},
            status="pending",
        )
    )
