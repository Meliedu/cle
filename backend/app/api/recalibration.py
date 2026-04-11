import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
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
    summaries: list[RecalibrationContentTypeSummary] = []
    transition_matrices: dict[str, dict[str, dict[str, float]]] = {}

    for ct in CONTENT_TYPES:
        # Count items_scanned: total recalibration_stats rows for this course+content_type
        stats_result = await db.execute(
            select(RecalibrationStats).where(
                RecalibrationStats.course_id == course_id,
                RecalibrationStats.content_type == ct,
            )
        )
        stats_rows = stats_result.scalars().all()
        items_scanned = len(stats_rows)

        # Count items_relabeled: pool items with recalibrated_difficulty IS NOT NULL
        relabeled_result = await db.execute(
            select(RevisionPoolItem).where(
                RevisionPoolItem.course_id == course_id,
                RevisionPoolItem.content_type == ct,
                RevisionPoolItem.recalibrated_difficulty.is_not(None),
            )
        )
        items_relabeled = len(relabeled_result.scalars().all())

        relabel_pct = (items_relabeled / items_scanned * 100.0) if items_scanned > 0 else 0.0

        # Load RecalibrationModel for transition_matrix and last_run
        model_result = await db.execute(
            select(RecalibrationModel).where(
                RecalibrationModel.course_id == course_id,
                RecalibrationModel.content_type == ct,
            )
        )
        model = model_result.scalar_one_or_none()

        last_run: str | None = None
        if model:
            last_run = model.updated_at.isoformat() if model.updated_at else None
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
    # Build join query: recalibration_stats joined with revision_pool_items
    stmt = (
        select(RecalibrationStats, RevisionPoolItem)
        .join(
            RevisionPoolItem,
            RevisionPoolItem.id == RecalibrationStats.pool_item_id,
        )
        .where(RecalibrationStats.course_id == course_id)
    )

    if content_type:
        stmt = stmt.where(RecalibrationStats.content_type == content_type)
    if llm_difficulty:
        stmt = stmt.where(RecalibrationStats.llm_difficulty == llm_difficulty)
    if recalibrated_only:
        stmt = stmt.where(RevisionPoolItem.recalibrated_difficulty.is_not(None))

    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)

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

    return APIResponse(
        success=True,
        data=RecalibrationItemsResponse(items=items),
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
