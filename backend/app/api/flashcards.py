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
from app.models.flashcard import (
    FlashcardCard,
    FlashcardFolder,
    FlashcardProgress,
    FlashcardSet,
)
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
    FlashcardFolderCreate,
    FlashcardFolderMove,
    FlashcardFolderRename,
    FlashcardFolderResponse,
    FlashcardProgressResponse,
    FlashcardProgressUpdate,
    FlashcardSetDetailResponse,
    FlashcardSetMove,
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
            folder_id=fc_set.folder_id,
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
            folder_id=fc_set.folder_id,
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


# ---------------------------------------------------------------------------
# Flashcard folders
# ---------------------------------------------------------------------------

# Maximum nesting depth for folder trees. Prevents unbounded recursion / DoS
# via deeply nested structures and keeps UI breadcrumbs sane.
MAX_FOLDER_DEPTH = 10


async def _fc_folder_ancestor_depth(
    db: AsyncSession, parent_id: uuid.UUID
) -> int:
    """Return the depth of ``parent_id`` (root = depth 1). Guards against cycles."""
    depth = 1
    current: uuid.UUID | None = parent_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if current in visited:
            return MAX_FOLDER_DEPTH + 1
        visited.add(current)
        parent = await db.get(FlashcardFolder, current)
        if parent is None or parent.deleted_at is not None:
            break
        if parent.parent_id is None:
            break
        depth += 1
        if depth > MAX_FOLDER_DEPTH:
            return depth
        current = parent.parent_id
    return depth


async def _fc_folder_descendant_ids(
    db: AsyncSession, root_id: uuid.UUID
) -> set[uuid.UUID]:
    result: set[uuid.UUID] = {root_id}
    frontier = [root_id]
    while frontier:
        rows = (
            await db.execute(
                select(FlashcardFolder.id).where(
                    FlashcardFolder.parent_id.in_(frontier),
                    FlashcardFolder.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        frontier = [r for r in rows if r not in result]
        result.update(frontier)
    return result


@router.get(
    "/courses/{course_id}/flashcard-folders",
    response_model=APIResponse[list[FlashcardFolderResponse]],
)
async def list_flashcard_folders(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, course_id, user.id)
    result = await db.execute(
        select(FlashcardFolder)
        .where(
            FlashcardFolder.course_id == course_id,
            FlashcardFolder.deleted_at.is_(None),
        )
        .order_by(FlashcardFolder.created_at)
    )
    return APIResponse(
        success=True,
        data=[FlashcardFolderResponse.model_validate(f) for f in result.scalars().all()],
    )


@router.post(
    "/courses/{course_id}/flashcard-folders",
    response_model=APIResponse[FlashcardFolderResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_flashcard_folder(
    course_id: uuid.UUID,
    body: FlashcardFolderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_enrollment(db, course_id, user.id)
    if body.parent_id is not None:
        parent = await db.get(FlashcardFolder, body.parent_id)
        if (
            parent is None
            or parent.deleted_at is not None
            or parent.course_id != course_id
        ):
            raise HTTPException(status_code=400, detail="Parent folder not found in this course")
        parent_depth = await _fc_folder_ancestor_depth(db, parent.id)
        if parent_depth >= MAX_FOLDER_DEPTH:
            raise HTTPException(
                status_code=400,
                detail=f"Folder nesting exceeds maximum depth of {MAX_FOLDER_DEPTH}",
            )
    folder = FlashcardFolder(
        course_id=course_id,
        name=body.name.strip() or "Untitled",
        parent_id=body.parent_id,
        created_by=user.id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return APIResponse(success=True, data=FlashcardFolderResponse.model_validate(folder))


@router.patch(
    "/flashcard-folders/{folder_id}",
    response_model=APIResponse[FlashcardFolderResponse],
)
async def rename_flashcard_folder(
    folder_id: uuid.UUID,
    body: FlashcardFolderRename,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    folder = await db.get(FlashcardFolder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, folder.course_id, user.id)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    folder.name = name
    await db.commit()
    await db.refresh(folder)
    return APIResponse(success=True, data=FlashcardFolderResponse.model_validate(folder))


@router.post(
    "/flashcard-folders/{folder_id}/move",
    response_model=APIResponse[FlashcardFolderResponse],
)
async def move_flashcard_folder(
    folder_id: uuid.UUID,
    body: FlashcardFolderMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    folder = await db.get(FlashcardFolder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, folder.course_id, user.id)
    if body.parent_id is not None:
        if body.parent_id == folder_id:
            raise HTTPException(status_code=400, detail="Cannot nest folder inside itself")
        parent = await db.get(FlashcardFolder, body.parent_id)
        if (
            parent is None
            or parent.deleted_at is not None
            or parent.course_id != folder.course_id
        ):
            raise HTTPException(status_code=400, detail="Parent folder not found in this course")
        descendants = await _fc_folder_descendant_ids(db, folder_id)
        if body.parent_id in descendants:
            raise HTTPException(status_code=400, detail="Cannot move folder into its own descendant")
        parent_depth = await _fc_folder_ancestor_depth(db, parent.id)
        if parent_depth >= MAX_FOLDER_DEPTH:
            raise HTTPException(
                status_code=400,
                detail=f"Folder nesting exceeds maximum depth of {MAX_FOLDER_DEPTH}",
            )
        # Note: FlashcardFolder has no `purpose` column today, so no
        # purpose-equality check is enforced here. Intentional asymmetry with
        # QuizFolder pending schema evolution.
    folder.parent_id = body.parent_id
    await db.commit()
    await db.refresh(folder)
    return APIResponse(success=True, data=FlashcardFolderResponse.model_validate(folder))


@router.delete(
    "/flashcard-folders/{folder_id}",
    response_model=APIResponse[None],
)
async def delete_flashcard_folder(
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    folder = await db.get(FlashcardFolder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, folder.course_id, user.id)

    # Reparent to this folder's parent, but only if the parent is still live.
    new_parent: uuid.UUID | None = folder.parent_id
    if new_parent is not None:
        gp = await db.get(FlashcardFolder, new_parent)
        if gp is None or gp.deleted_at is not None:
            new_parent = None

    # Group the reparent writes + soft-delete inside a SAVEPOINT so a failure
    # mid-way can't leave the table in a half-updated state.
    async with db.begin_nested():
        await db.execute(
            FlashcardSet.__table__.update()
            .where(FlashcardSet.folder_id == folder_id)
            .values(folder_id=new_parent)
        )
        await db.execute(
            FlashcardFolder.__table__.update()
            .where(FlashcardFolder.parent_id == folder_id)
            .values(parent_id=new_parent)
        )
        folder.deleted_at = datetime.now(timezone.utc)

    await db.commit()
    return APIResponse(success=True, data=None)


@router.patch(
    "/flashcard-sets/{set_id}/folder",
    response_model=APIResponse[FlashcardSetResponse],
)
async def move_flashcard_set_to_folder(
    set_id: uuid.UUID,
    body: FlashcardSetMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    fc_set = await db.get(FlashcardSet, set_id)
    if fc_set is None or fc_set.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Flashcard set not found")
    await _verify_enrollment(db, fc_set.course_id, user.id)
    if body.folder_id is not None:
        folder = await db.get(FlashcardFolder, body.folder_id)
        if (
            folder is None
            or folder.deleted_at is not None
            or folder.course_id != fc_set.course_id
        ):
            raise HTTPException(status_code=400, detail="Folder not found in this course")
    fc_set.folder_id = body.folder_id
    await db.commit()
    await db.refresh(fc_set)

    count_stmt = select(func.count(FlashcardCard.id)).where(
        FlashcardCard.flashcard_set_id == fc_set.id
    )
    card_count = (await db.execute(count_stmt)).scalar_one()

    return APIResponse(
        success=True,
        data=FlashcardSetResponse(
            id=fc_set.id,
            course_id=fc_set.course_id,
            title=fc_set.title,
            is_published=fc_set.is_published,
            folder_id=fc_set.folder_id,
            card_count=card_count,
            created_at=fc_set.created_at,
        ),
    )
