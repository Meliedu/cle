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
    """Require an active enrollment in a non-soft-deleted course.

    Joins to ``Course`` so soft-deleted courses fail verification in a single
    query, avoiding the stale-course / stale-enrollment gap that would appear
    if we checked enrollment alone.
    """
    result = await db.execute(
        select(Enrollment)
        .join(Course, Course.id == Enrollment.course_id)
        .where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
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
    """Require an active instructor-role enrollment in a non-soft-deleted course.

    Raises 403 if the user is not enrolled as an instructor in the course or
    if the course itself has been soft-deleted. Use this for operations that
    must be restricted to instructors of the specific course (e.g. importing
    to the live question bank).
    """
    result = await db.execute(
        select(Enrollment)
        .join(Course, Course.id == Enrollment.course_id)
        .where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
            Enrollment.role == "instructor",
            Course.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enrolled as an instructor in this course",
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
