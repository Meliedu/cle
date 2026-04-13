import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models.course import Course
from app.models.recalibration import RecalibrationModel, RecalibrationStats
from app.models.revision import RevisionPoolItem
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.recalibration import (
    RecalibrationContentTypeSummary,
    RecalibrationItemRow,
    RecalibrationItemsResponse,
    RecalibrationOverviewResponse,
)

router = APIRouter(tags=["recalibration"])

CONTENT_TYPES = ["quiz", "flashcard", "speaking"]


async def _verify_course_ownership(
    db: AsyncSession, course_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Verify that the user is the instructor owner of the course. Raises 404 if not."""
    result = await db.execute(
        select(Course.id).where(
            Course.id == course_id,
            Course.instructor_id == user_id,
            Course.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )


def _truncate(text: str | None, length: int = 80) -> str:
    if not text:
        return ""
    return text[:length] + ("..." if len(text) > length else "")


def _item_preview(item: RevisionPoolItem) -> str:
    if item.content_type == "quiz":
        return _truncate(item.question_text)
    elif item.content_type == "flashcard":
        return _truncate(item.front)
    else:
        return _truncate(item.target_text)


@router.get(
    "/courses/{course_id}/recalibration/overview",
    response_model=APIResponse[RecalibrationOverviewResponse],
)
async def get_recalibration_overview(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_course_ownership(db, course_id, user.id)
    # Aggregate per content_type with three queries (was 3*N before).
    scanned_rows = (
        await db.execute(
            select(RecalibrationStats.content_type, func.count())
            .where(RecalibrationStats.course_id == course_id)
            .group_by(RecalibrationStats.content_type)
        )
    ).all()
    scanned_map = {ct: cnt for ct, cnt in scanned_rows}

    relabeled_rows = (
        await db.execute(
            select(RevisionPoolItem.content_type, func.count())
            .where(
                RevisionPoolItem.course_id == course_id,
                RevisionPoolItem.recalibrated_difficulty.is_not(None),
            )
            .group_by(RevisionPoolItem.content_type)
        )
    ).all()
    relabeled_map = {ct: cnt for ct, cnt in relabeled_rows}

    model_rows = (
        await db.execute(
            select(RecalibrationModel).where(RecalibrationModel.course_id == course_id)
        )
    ).scalars().all()
    model_map = {m.content_type: m for m in model_rows}

    summaries: list[RecalibrationContentTypeSummary] = []
    transition_matrices: dict[str, dict[str, dict[str, float]]] = {}

    for ct in CONTENT_TYPES:
        items_scanned = scanned_map.get(ct, 0)
        items_relabeled = relabeled_map.get(ct, 0)
        relabel_pct = (items_relabeled / items_scanned * 100.0) if items_scanned > 0 else 0.0
        model = model_map.get(ct)
        last_run = model.updated_at.isoformat() if (model and model.updated_at) else None
        if model:
            transition_matrices[ct] = model.transition_matrix or {}
        summaries.append(
            RecalibrationContentTypeSummary(
                content_type=ct,
                items_scanned=items_scanned,
                items_relabeled=items_relabeled,
                relabel_pct=round(relabel_pct, 1),
                last_run=last_run,
            )
        )

    return APIResponse(
        success=True,
        data=RecalibrationOverviewResponse(
            summaries=summaries,
            transition_matrices=transition_matrices,
        ),
    )


@router.get(
    "/courses/{course_id}/recalibration/items",
    response_model=APIResponse[RecalibrationItemsResponse],
)
async def get_recalibration_items(
    course_id: uuid.UUID,
    content_type: str | None = Query(default=None),
    llm_difficulty: str | None = Query(default=None),
    recalibrated_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_course_ownership(db, course_id, user.id)
    if content_type is not None and content_type not in CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"content_type must be one of {CONTENT_TYPES}",
        )
    if llm_difficulty is not None and llm_difficulty not in {"easy", "medium", "hard"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="llm_difficulty must be one of easy, medium, hard",
        )

    base_filters = [RecalibrationStats.course_id == course_id]
    if content_type:
        base_filters.append(RecalibrationStats.content_type == content_type)
    if llm_difficulty:
        base_filters.append(RecalibrationStats.llm_difficulty == llm_difficulty)

    join_filters: list = []
    if recalibrated_only:
        join_filters.append(RevisionPoolItem.recalibrated_difficulty.is_not(None))

    count_stmt = (
        select(func.count())
        .select_from(RecalibrationStats)
        .join(RevisionPoolItem, RevisionPoolItem.id == RecalibrationStats.pool_item_id)
        .where(*base_filters, *join_filters)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(RecalibrationStats, RevisionPoolItem)
        .join(RevisionPoolItem, RevisionPoolItem.id == RecalibrationStats.pool_item_id)
        .where(*base_filters, *join_filters)
        .order_by(RecalibrationStats.id)
        .offset((page - 1) * limit)
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    items: list[RecalibrationItemRow] = []
    for stats, pool_item in rows:
        correct_rate = (
            float(stats.correct_count) / float(stats.attempt_count)
            if stats.attempt_count > 0
            else 0.0
        )
        items.append(
            RecalibrationItemRow(
                pool_item_id=str(pool_item.id),
                content_type=pool_item.content_type,
                item_preview=_item_preview(pool_item),
                llm_difficulty=stats.llm_difficulty,
                recalibrated_difficulty=pool_item.recalibrated_difficulty,
                confidence=(
                    float(pool_item.recalibration_confidence)
                    if pool_item.recalibration_confidence is not None
                    else None
                ),
                attempt_count=stats.attempt_count,
                correct_rate=round(correct_rate, 3),
                instructor_override=pool_item.instructor_override,
            )
        )

    pages = (total + limit - 1) // limit if total else 0
    return APIResponse(
        success=True,
        data=RecalibrationItemsResponse(
            items=items, total=total, page=page, limit=limit, pages=pages
        ),
    )


@router.post(
    "/courses/{course_id}/recalibration/items/{item_id}/override",
    response_model=APIResponse[dict],
)
async def toggle_instructor_override(
    course_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_course_ownership(db, course_id, user.id)
    result = await db.execute(
        select(RevisionPoolItem).where(
            RevisionPoolItem.id == item_id,
            RevisionPoolItem.course_id == course_id,
        )
    )
    pool_item = result.scalar_one_or_none()

    if not pool_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pool item not found",
        )

    # Toggle instructor_override
    new_override = not pool_item.instructor_override
    pool_item.instructor_override = new_override

    # If override enabled: clear recalibrated_difficulty and recalibration_confidence
    if new_override:
        pool_item.recalibrated_difficulty = None
        pool_item.recalibration_confidence = None

    await db.commit()

    return APIResponse(
        success=True,
        data={
            "pool_item_id": str(pool_item.id),
            "instructor_override": new_override,
            "recalibrated_difficulty": pool_item.recalibrated_difficulty,
        },
    )
