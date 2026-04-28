import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models import Course, CourseModule, User
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    CourseModuleCreate,
    CourseModuleResponse,
    CourseModuleUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/modules", tags=["curriculum"])


async def _own_course(
    course_id: uuid.UUID, user: User, db: AsyncSession
) -> Course:
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    return course


@router.post("", response_model=APIResponse[CourseModuleResponse], status_code=201)
async def create_module(
    course_id: uuid.UUID,
    body: CourseModuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CourseModuleResponse]:
    await _own_course(course_id, user, db)
    module = CourseModule(course_id=course_id, **body.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return APIResponse(success=True, data=CourseModuleResponse.model_validate(module))


@router.get("", response_model=APIResponse[list[CourseModuleResponse]])
async def list_modules(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[list[CourseModuleResponse]]:
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseModule)
        .where(
            CourseModule.course_id == course_id,
            CourseModule.deleted_at.is_(None),
        )
        .order_by(CourseModule.order_index)
    )
    modules = result.scalars().all()
    return APIResponse(
        success=True,
        data=[CourseModuleResponse.model_validate(m) for m in modules],
    )


@router.put("/{module_id}", response_model=APIResponse[CourseModuleResponse])
async def update_module(
    course_id: uuid.UUID,
    module_id: uuid.UUID,
    body: CourseModuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CourseModuleResponse]:
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseModule).where(
            CourseModule.id == module_id,
            CourseModule.course_id == course_id,
            CourseModule.deleted_at.is_(None),
        )
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Module not found"
        )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(module, field, value)
    await db.commit()
    await db.refresh(module)
    return APIResponse(success=True, data=CourseModuleResponse.model_validate(module))


@router.delete("/{module_id}", response_model=APIResponse[None])
async def delete_module(
    course_id: uuid.UUID,
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[None]:
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseModule).where(
            CourseModule.id == module_id,
            CourseModule.course_id == course_id,
            CourseModule.deleted_at.is_(None),
        )
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Module not found"
        )
    module.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)
