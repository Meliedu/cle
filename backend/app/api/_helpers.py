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


async def enqueue_next_actions_recompute(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> None:
    """Best-effort enqueue. Caller commits.

    Dedupe: if a pending/running materialize_next_actions task already exists
    for this (user, course), skip. The Task.payload column is JSON (not JSONB)
    so we use ``op('->>')`` for value extraction — see Phase 2 Task 16.
    """
    existing = (
        await db.execute(
            select(Task.id).where(
                Task.task_type == "materialize_next_actions",
                Task.status.in_(("pending", "running")),
                Task.payload.op("->>")("user_id") == str(user_id),
                Task.payload.op("->>")("course_id") == str(course_id),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        Task(
            task_type="materialize_next_actions",
            payload={"user_id": str(user_id), "course_id": str(course_id)},
            status="pending",
        )
    )
