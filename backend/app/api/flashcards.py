import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api._helpers import verify_enrollment as _verify_enrollment
from app.api.deps import get_current_user, get_db, require_instructor
from app.config import settings
from app.models.flashcard import FlashcardCard, FlashcardProgress, FlashcardSet
from app.models.scheduler import SchedulerModel
from app.models.user import User
from app.schemas.common import APIResponse
from app.services.gamification import award_xp
from app.services.scheduler import (
    DEFAULT_PARAMS,
    GRADE_MAP,
    SWITCHOVER_THRESHOLD,
    FSRSScheduler,
    initialize_from_sm2,
    sm2_update,
    update_parameters,
)
from app.schemas.flashcard import (
    FlashcardCardResponse,
    FlashcardProgressResponse,
    FlashcardProgressUpdate,
    FlashcardSetDetailResponse,
    FlashcardSetResponse,
)

router = APIRouter(tags=["flashcards"])


@router.get(
    "/courses/{course_id}/flashcard-sets",
    response_model=APIResponse[list[FlashcardSetResponse]],
)
async def list_flashcard_sets(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, course_id, user.id)

    stmt = (
        select(
            FlashcardSet,
            func.count(FlashcardCard.id).label("card_count"),
        )
        .outerjoin(FlashcardCard, FlashcardCard.flashcard_set_id == FlashcardSet.id)
        .where(
            FlashcardSet.course_id == course_id,
            FlashcardSet.deleted_at.is_(None),
        )
        .group_by(FlashcardSet.id)
    )

    if user.role != "instructor":
        stmt = stmt.where(FlashcardSet.is_published.is_(True))

    result = await db.execute(stmt)
    rows = result.all()

    data = [
        FlashcardSetResponse(
            id=fc_set.id,
            course_id=fc_set.course_id,
            title=fc_set.title,
            is_published=fc_set.is_published,
            card_count=card_count,
            created_at=fc_set.created_at,
        )
        for fc_set, card_count in rows
    ]

    return APIResponse(success=True, data=data)


@router.get(
    "/flashcard-sets/{set_id}",
    response_model=APIResponse[FlashcardSetDetailResponse],
)
async def get_flashcard_set(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(FlashcardSet)
        .options(selectinload(FlashcardSet.cards))
        .where(FlashcardSet.id == set_id, FlashcardSet.deleted_at.is_(None))
    )
    fc_set = result.scalar_one_or_none()
    if not fc_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcard set not found",
        )

    await _verify_enrollment(db, fc_set.course_id, user.id)

    if user.role != "instructor" and not fc_set.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcard set not found",
        )

    card_responses = [
        FlashcardCardResponse(
            id=c.id,
            card_index=c.card_index,
            front=c.front,
            back=c.back,
            created_at=c.created_at,
        )
        for c in fc_set.cards
    ]

    return APIResponse(
        success=True,
        data=FlashcardSetDetailResponse(
            id=fc_set.id,
            course_id=fc_set.course_id,
            title=fc_set.title,
            is_published=fc_set.is_published,
            cards=card_responses,
            created_at=fc_set.created_at,
        ),
    )


@router.post(
    "/flashcard-sets/{set_id}/publish",
    response_model=APIResponse[FlashcardSetResponse],
)
async def publish_flashcard_set(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(FlashcardSet).where(
            FlashcardSet.id == set_id,
            FlashcardSet.created_by == user.id,
            FlashcardSet.deleted_at.is_(None),
        )
    )
    fc_set = result.scalar_one_or_none()
    if not fc_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcard set not found",
        )

    fc_set.is_published = not fc_set.is_published
    await db.commit()
    await db.refresh(fc_set)

    count_result = await db.execute(
        select(func.count(FlashcardCard.id)).where(
            FlashcardCard.flashcard_set_id == fc_set.id
        )
    )
    card_count = count_result.scalar_one()

    return APIResponse(
        success=True,
        data=FlashcardSetResponse(
            id=fc_set.id,
            course_id=fc_set.course_id,
            title=fc_set.title,
            is_published=fc_set.is_published,
            card_count=card_count,
            created_at=fc_set.created_at,
        ),
    )


@router.delete(
    "/flashcard-sets/{set_id}",
    response_model=APIResponse[None],
)
async def delete_flashcard_set(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(FlashcardSet).where(
            FlashcardSet.id == set_id,
            FlashcardSet.created_by == user.id,
            FlashcardSet.deleted_at.is_(None),
        )
    )
    fc_set = result.scalar_one_or_none()
    if not fc_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcard set not found",
        )

    fc_set.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.put(
    "/flashcard-sets/{set_id}/progress",
    response_model=APIResponse[FlashcardProgressResponse],
)
async def update_progress(
    set_id: uuid.UUID,
    body: FlashcardProgressUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify the set exists and user is enrolled
    set_result = await db.execute(
        select(FlashcardSet).where(
            FlashcardSet.id == set_id,
            FlashcardSet.deleted_at.is_(None),
        )
    )
    fc_set = set_result.scalar_one_or_none()
    if not fc_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcard set not found",
        )

    await _verify_enrollment(db, fc_set.course_id, user.id)

    # Verify the card belongs to this set
    card_result = await db.execute(
        select(FlashcardCard).where(
            FlashcardCard.id == body.card_id,
            FlashcardCard.flashcard_set_id == set_id,
        )
    )
    if not card_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found in this set",
        )

    # Get or create progress record
    progress_result = await db.execute(
        select(FlashcardProgress).where(
            FlashcardProgress.user_id == user.id,
            FlashcardProgress.flashcard_card_id == body.card_id,
        )
    )
    progress = progress_result.scalar_one_or_none()

    if progress is None:
        progress = FlashcardProgress(
            user_id=user.id,
            flashcard_card_id=body.card_id,
            ease_factor=Decimal("2.50"),
            interval_days=0,
            repetitions=0,
        )
        db.add(progress)

    now = datetime.now(timezone.utc)

    sched_result = await db.execute(
        select(SchedulerModel).where(
            SchedulerModel.user_id == user.id,
            SchedulerModel.course_id == fc_set.course_id,
        )
    )
    sched_model = sched_result.scalar_one_or_none()
    if sched_model is None:
        sched_model = SchedulerModel(
            user_id=user.id,
            course_id=fc_set.course_id,
            parameters=list(DEFAULT_PARAMS),
            strategy="sm2",
            review_count=0,
        )
        db.add(sched_model)

    use_fsrs = (
        settings.fsrs_enabled
        and sched_model.review_count >= SWITCHOVER_THRESHOLD
    )

    if use_fsrs:
        # FSRS path
        grade = GRADE_MAP.get(body.quality, 3)
        scheduler = FSRSScheduler(sched_model.parameters)

        # Compute elapsed days since last review
        elapsed = 0.0
        if progress.last_reviewed is not None:
            elapsed = (now - progress.last_reviewed).total_seconds() / 86400.0

        # Handle switchover: initialize FSRS state from SM-2 if needed
        if sched_model.strategy == "sm2":
            stability, difficulty = initialize_from_sm2(
                float(progress.ease_factor), progress.interval_days
            )
            progress.stability = stability
            progress.difficulty = difficulty
            sched_model.strategy = "fsrs"

        # Coerce FSRS state to float (guard against Decimal leaking in from DB layer)
        s_float = float(progress.stability) if progress.stability is not None else None
        d_float = float(progress.difficulty) if progress.difficulty is not None else None

        # Online parameter update
        if s_float is not None and elapsed > 0:
            predicted_r = scheduler.compute_retrievability(elapsed, s_float)
            actual_recall = grade >= 2
            sched_model.parameters = update_parameters(
                sched_model.parameters,
                predicted_r,
                actual_recall,
                stability=s_float,
                difficulty=d_float if d_float is not None else 5.0,
                elapsed_days=elapsed,
                grade=grade,
            )
            scheduler = FSRSScheduler(sched_model.parameters)

        # State transition
        new_s, new_d, interval = scheduler.next_state(
            grade=grade,
            stability=s_float,
            difficulty=d_float,
            elapsed_days=elapsed,
        )
        progress.stability = new_s
        progress.difficulty = new_d
        progress.last_grade = grade
        progress.interval_days = interval
        progress.next_review = now + timedelta(days=interval)
    else:
        # SM-2 path (unchanged logic)
        q = body.quality
        ef = float(progress.ease_factor)
        new_ef, new_interval, new_reps = sm2_update(q, ef, progress.interval_days, progress.repetitions)
        progress.ease_factor = Decimal(str(round(new_ef, 2)))
        progress.interval_days = new_interval
        progress.repetitions = new_reps
        progress.next_review = now + timedelta(days=new_interval)

    progress.last_reviewed = now
    progress.fsrs_review_count = (progress.fsrs_review_count or 0) + 1
    sched_model.review_count = sched_model.review_count + 1

    await db.commit()
    await db.refresh(progress)

    # Award XP for flashcard review
    await award_xp(
        db,
        user_id=user.id,
        course_id=fc_set.course_id,
        xp=50,
        activity="flashcard",
    )
    await db.commit()

    return APIResponse(
        success=True,
        data=FlashcardProgressResponse(
            card_id=progress.flashcard_card_id,
            ease_factor=progress.ease_factor,
            interval_days=progress.interval_days,
            repetitions=progress.repetitions,
            next_review=progress.next_review,
            last_reviewed=progress.last_reviewed,
        ),
    )
