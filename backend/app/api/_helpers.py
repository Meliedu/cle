import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Enrollment


async def verify_enrollment(
    db: AsyncSession,
    course_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
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
    """Require an active instructor-role enrollment for the given user/course.

    Raises 403 if the user is not enrolled as an instructor in the course.
    Use this for operations that must be restricted to instructors of the
    specific course (e.g. importing to the live question bank).
    """
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
            Enrollment.role == "instructor",
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enrolled as an instructor in this course",
        )
