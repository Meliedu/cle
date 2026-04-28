import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course
from app.models import CourseModule
from app.models.course import Course
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    CourseModuleCreate,
    CourseModuleResponse,
    CourseModuleUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/modules", tags=["curriculum"])


@router.post("", response_model=APIResponse[CourseModuleResponse], status_code=201)
async def create_module(
    body: CourseModuleCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[CourseModuleResponse]:
    # Fix 10: validate parent_id belongs to the same course
    if body.parent_id is not None:
        parent = (
            await db.execute(
                select(CourseModule).where(
                    CourseModule.id == body.parent_id,
                    CourseModule.course_id == course.id,
                    CourseModule.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent module not found",
            )
    module = CourseModule(course_id=course.id, **body.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return APIResponse(success=True, data=CourseModuleResponse.model_validate(module))


@router.get("", response_model=APIResponse[list[CourseModuleResponse]])
async def list_modules(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[CourseModuleResponse]]:
    result = await db.execute(
        select(CourseModule)
        .where(
            CourseModule.course_id == course.id,
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
    module_id: uuid.UUID,
    body: CourseModuleUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[CourseModuleResponse]:
    # Fix 10: validate parent_id belongs to the same course
    if body.parent_id is not None:
        parent = (
            await db.execute(
                select(CourseModule).where(
                    CourseModule.id == body.parent_id,
                    CourseModule.course_id == course.id,
                    CourseModule.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent module not found",
            )
    result = await db.execute(
        select(CourseModule).where(
            CourseModule.id == module_id,
            CourseModule.course_id == course.id,
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
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[None]:
    result = await db.execute(
        select(CourseModule).where(
            CourseModule.id == module_id,
            CourseModule.course_id == course.id,
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
