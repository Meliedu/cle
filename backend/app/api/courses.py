import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.models.course import Course, Enrollment
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.course import CourseCreate, CourseResponse, CourseUpdate

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("", response_model=APIResponse[CourseResponse], status_code=201)
async def create_course(
    body: CourseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    course = Course(
        name=body.name,
        code=body.code,
        description=body.description,
        language=body.language,
        semester=body.semester,
        settings=body.settings,
        instructor_id=user.id,
    )
    db.add(course)
    await db.flush()

    enrollment = Enrollment(course_id=course.id, user_id=user.id, role="instructor")
    db.add(enrollment)

    await db.commit()
    await db.refresh(course)
    return APIResponse(success=True, data=CourseResponse.model_validate(course))


@router.get("", response_model=APIResponse[list[CourseResponse]])
async def list_courses(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user.id, Course.deleted_at.is_(None))
    )
    courses = result.scalars().all()
    return APIResponse(
        success=True,
        data=[CourseResponse.model_validate(c) for c in courses],
    )


@router.get("/{course_id}", response_model=APIResponse[CourseResponse])
async def get_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user.id
        )
    )
    if not enrollment.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    return APIResponse(success=True, data=CourseResponse.model_validate(course))


@router.put("/{course_id}", response_model=APIResponse[CourseResponse])
async def update_course(
    course_id: uuid.UUID,
    body: CourseUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(course, field, value)

    await db.commit()
    await db.refresh(course)
    return APIResponse(success=True, data=CourseResponse.model_validate(course))


@router.delete("/{course_id}", response_model=APIResponse[None])
async def delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    course.deleted_at = datetime.now()
    await db.commit()
    return APIResponse(success=True, data=None)


@router.post("/{course_id}/enroll", response_model=APIResponse[None], status_code=201)
async def enroll_in_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already enrolled")

    enrollment = Enrollment(course_id=course_id, user_id=user.id, role=user.role)
    db.add(enrollment)
    await db.commit()
    return APIResponse(success=True, data=None)
