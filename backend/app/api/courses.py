import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.models.course import Course, Enrollment
from app.models.user import User
from app.schemas.common import APIResponse, PaginatedResponse, PaginationMeta
from app.schemas.course import (
    CourseCreate,
    CourseResponse,
    CourseUpdate,
    EnrollByCodeRequest,
)

# Avoid ambiguous chars (0/O, 1/I/L). Uppercase so codes are easy to dictate.
_ENROLL_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_ENROLL_CODE_LENGTH = 8


def _generate_enroll_code() -> str:
    return "".join(
        secrets.choice(_ENROLL_CODE_ALPHABET) for _ in range(_ENROLL_CODE_LENGTH)
    )


def _normalize_enroll_code(raw: str) -> str:
    return "".join(ch for ch in raw.upper() if ch.isalnum())

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("", response_model=APIResponse[CourseResponse], status_code=201)
async def create_course(
    body: CourseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    # Retry a handful of times on the astronomically unlikely code collision.
    for _ in range(5):
        course = Course(
            name=body.name,
            code=body.code,
            description=body.description,
            language=body.language,
            semester=body.semester,
            settings=body.settings,
            instructor_id=user.id,
            enroll_code=_generate_enroll_code(),
        )
        db.add(course)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            continue

        enrollment = Enrollment(
            course_id=course.id, user_id=user.id, role="instructor"
        )
        db.add(enrollment)
        await db.commit()
        await db.refresh(course)
        return APIResponse(success=True, data=CourseResponse.model_validate(course))

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Could not allocate enrollment code, please retry",
    )


@router.get("", response_model=PaginatedResponse[CourseResponse])
async def list_courses(
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if page < 1 or limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination: page >= 1, 1 <= limit <= 100",
        )

    base = (
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user.id, Course.deleted_at.is_(None))
    )

    count_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = int(count_result.scalar() or 0)

    result = await db.execute(
        base.order_by(Course.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    courses = result.scalars().all()
    pages = (total + limit - 1) // limit if total else 0
    return PaginatedResponse(
        success=True,
        data=[CourseResponse.model_validate(c) for c in courses],
        meta=PaginationMeta(total=total, page=page, limit=limit, pages=pages),
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

    course.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.post(
    "/enroll-by-code",
    response_model=APIResponse[CourseResponse],
    status_code=201,
)
async def enroll_by_code(
    body: EnrollByCodeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    code = _normalize_enroll_code(body.enroll_code)
    if len(code) != _ENROLL_CODE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid enrollment code format",
        )

    result = await db.execute(
        select(Course).where(
            Course.enroll_code == code, Course.deleted_at.is_(None)
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No course found for that code",
        )

    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course.id, Enrollment.user_id == user.id
        )
    )
    if existing.scalar_one_or_none():
        # Idempotent: already enrolled → return the course so the client can
        # just navigate into it.
        return APIResponse(success=True, data=CourseResponse.model_validate(course))

    enrollment = Enrollment(course_id=course.id, user_id=user.id, role=user.role)
    db.add(enrollment)
    await db.commit()
    return APIResponse(success=True, data=CourseResponse.model_validate(course))


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
