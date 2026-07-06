"""Score-category CRUD router (Task 10): the score-policy setup step (T024).

P1 subset of the spec ``scores.py``: ``GET/POST/PATCH/DELETE
/courses/{id}/score-categories``. Categories are seeded from the pilot profile on
course creation (Task 4); this router lets the teacher view/edit/add/remove/
reorder them. Every route is guarded by ``get_owned_course`` (instructor +
ownership) so students get 403 and non-owners get 404. DELETE is a soft delete.
Grade export + student scores are P5.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course
from app.models.course import Course
from app.models.score import ScoreCategory
from app.schemas.common import APIResponse
from app.schemas.score import (
    ScoreCategoryCreate,
    ScoreCategoryResponse,
    ScoreCategoryUpdate,
)

router = APIRouter(
    prefix="/courses/{course_id}/score-categories", tags=["setup"]
)


async def _get_category(
    db: AsyncSession, course: Course, category_id: uuid.UUID
) -> ScoreCategory:
    result = await db.execute(
        select(ScoreCategory).where(
            ScoreCategory.id == category_id,
            ScoreCategory.course_id == course.id,
            ScoreCategory.deleted_at.is_(None),
        )
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Score category not found"
        )
    return cat


@router.get("", response_model=APIResponse[list[ScoreCategoryResponse]])
async def list_score_categories(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[ScoreCategoryResponse]]:
    result = await db.execute(
        select(ScoreCategory)
        .where(
            ScoreCategory.course_id == course.id,
            ScoreCategory.deleted_at.is_(None),
        )
        .order_by(ScoreCategory.sort, ScoreCategory.created_at)
    )
    cats = result.scalars().all()
    return APIResponse(
        success=True,
        data=[ScoreCategoryResponse.model_validate(c) for c in cats],
    )


@router.post("", response_model=APIResponse[ScoreCategoryResponse], status_code=201)
async def create_score_category(
    body: ScoreCategoryCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[ScoreCategoryResponse]:
    if body.sort is not None:
        next_sort = body.sort
    else:
        # Append after the current highest sort among live categories.
        max_sort = (
            await db.execute(
                select(func.max(ScoreCategory.sort)).where(
                    ScoreCategory.course_id == course.id,
                    ScoreCategory.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        next_sort = 0 if max_sort is None else max_sort + 1

    cat = ScoreCategory(
        course_id=course.id,
        name=body.name,
        weight=body.weight,
        points_pool=body.points_pool,
        sort=next_sort,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return APIResponse(success=True, data=ScoreCategoryResponse.model_validate(cat))


@router.patch(
    "/{category_id}", response_model=APIResponse[ScoreCategoryResponse]
)
async def update_score_category(
    category_id: uuid.UUID,
    body: ScoreCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[ScoreCategoryResponse]:
    cat = await _get_category(db, course, category_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)
    await db.commit()
    await db.refresh(cat)
    return APIResponse(success=True, data=ScoreCategoryResponse.model_validate(cat))


@router.delete("/{category_id}", response_model=APIResponse[None])
async def delete_score_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[None]:
    cat = await _get_category(db, course, category_id)
    cat.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)
