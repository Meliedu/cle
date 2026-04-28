import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course
from app.models import LearningObjective
from app.models.course import Course
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    LearningObjectiveCreate,
    LearningObjectiveResponse,
    LearningObjectiveUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/objectives", tags=["curriculum"])


def _validate_scope(body: LearningObjectiveCreate | LearningObjectiveUpdate) -> None:
    if body.module_id is not None and body.meeting_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="objective cannot be scoped to both module and meeting",
        )


@router.post("", response_model=APIResponse[LearningObjectiveResponse], status_code=201)
async def create_objective(
    body: LearningObjectiveCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[LearningObjectiveResponse]:
    _validate_scope(body)
    obj = LearningObjective(course_id=course.id, **body.model_dump())
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="objective scope invalid")
    await db.refresh(obj)
    return APIResponse(success=True, data=LearningObjectiveResponse.model_validate(obj))


@router.get("", response_model=APIResponse[list[LearningObjectiveResponse]])
async def list_objectives(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[LearningObjectiveResponse]]:
    result = await db.execute(
        select(LearningObjective)
        .where(
            LearningObjective.course_id == course.id,
            LearningObjective.deleted_at.is_(None),
        )
        .order_by(LearningObjective.order_index)
    )
    objs = result.scalars().all()
    return APIResponse(
        success=True,
        data=[LearningObjectiveResponse.model_validate(o) for o in objs],
    )


@router.put("/{objective_id}", response_model=APIResponse[LearningObjectiveResponse])
async def update_objective(
    objective_id: uuid.UUID,
    body: LearningObjectiveUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[LearningObjectiveResponse]:
    _validate_scope(body)
    result = await db.execute(
        select(LearningObjective).where(
            LearningObjective.id == objective_id,
            LearningObjective.course_id == course.id,
            LearningObjective.deleted_at.is_(None),
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Objective not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return APIResponse(success=True, data=LearningObjectiveResponse.model_validate(obj))


@router.delete("/{objective_id}", response_model=APIResponse[None])
async def delete_objective(
    objective_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[None]:
    result = await db.execute(
        select(LearningObjective).where(
            LearningObjective.id == objective_id,
            LearningObjective.course_id == course.id,
            LearningObjective.deleted_at.is_(None),
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Objective not found")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)
