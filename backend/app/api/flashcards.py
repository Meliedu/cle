import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.learning_events import record_attempt_event

logger = logging.getLogger(__name__)

from app.api._helpers import (
    verify_enrollment as _verify_enrollment,
)
from app.api.deps import get_current_user, get_db, require_instructor
from app.config import settings
from app.models.flashcard import (
    FlashcardCard,
    FlashcardFolder,
    FlashcardProgress,
    FlashcardSet,
)
from app.models.scheduler import SchedulerModel
from app.models.task import Task
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
# FSRS rating → mastery outcome. ``quality`` from the request is SM-2 (0..5);
# we route through GRADE_MAP to FSRS (1..4) before looking up the outcome so
# the bucket boundaries match the spec (again=0, hard=0.4, good=0.8, easy=1).
# SM-2 quality values that don't appear in GRADE_MAP (1, 3) collapse to the
# nearest "again" or "good" bucket via _quality_to_fsrs below.
_FSRS_GRADE_TO_OUTCOME = {1: 0.0, 2: 0.4, 3: 0.8, 4: 1.0}


def _quality_to_outcome(quality: int) -> float:
    fsrs = GRADE_MAP.get(quality)
    if fsrs is None:
        # SM-2 quality 1 is between "again" and "hard" — fold to "again".
        # SM-2 quality 3 is "below good" — fold to "hard".
        if quality <= 1:
            fsrs = 1
        elif quality == 3:
            fsrs = 2
        else:
            fsrs = 3
    return _FSRS_GRADE_TO_OUTCOME.get(fsrs, 0.4)
from app.schemas.flashcard import (
    FlashcardCardCreate,
    FlashcardCardResponse,
    FlashcardCardUpdate,
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


def _enqueue_mastery_for_flashcard(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    card_id: uuid.UUID,
    quality: int,
) -> None:
    """Add a single ``update_concept_mastery`` Task row for a flashcard review."""
    outcome = _quality_to_outcome(quality)
    db.add(
        Task(
            task_type="update_concept_mastery",
            payload={
                "user_id": str(user_id),
                "course_id": str(course_id),
                "target_kind": "flashcard_card",
                "target_id": str(card_id),
                "outcome": outcome,
                "attempt_kind": "flashcard",
            },
            status="pending",
        )
    )


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
            difficulty=c.difficulty,
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

    # Enqueue mastery update after progress is durable. Failure here must not
    # roll back the student's review; we log and swallow.
    try:
        _enqueue_mastery_for_flashcard(
            db,
            user_id=user.id,
            course_id=fc_set.course_id,
            card_id=body.card_id,
            quality=body.quality,
        )
        await record_attempt_event(
            db,
            course_id=fc_set.course_id,
            user_id=user.id,
            source_kind="flashcard",
            source_id=progress.id,
            stage="review",
            value={"quality": body.quality},
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — non-fatal: progress already persisted
        logger.exception(
            "Failed to enqueue mastery update for card_id=%s user_id=%s",
            body.card_id,
            user.id,
        )
        await db.rollback()

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
# Per-card review actions (instructor-only)
# ---------------------------------------------------------------------------


@router.post(
    "/flashcard-sets/{set_id}/cards",
    response_model=APIResponse[FlashcardCardResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_flashcard_card(
    set_id: uuid.UUID,
    body: FlashcardCardCreate,
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
        raise HTTPException(status_code=404, detail="Flashcard set not found")

    count_result = await db.execute(
        select(func.count(FlashcardCard.id)).where(
            FlashcardCard.flashcard_set_id == set_id
        )
    )
    next_index = count_result.scalar_one()

    card = FlashcardCard(
        flashcard_set_id=set_id,
        card_index=next_index,
        front=body.front.strip()[:500],
        back=body.back.strip()[:2000],
        difficulty=body.difficulty,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return APIResponse(
        success=True, data=FlashcardCardResponse.model_validate(card)
    )


@router.delete(
    "/flashcard-cards/{card_id}",
    response_model=APIResponse[None],
)
async def delete_flashcard_card(
    card_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(FlashcardCard)
        .join(FlashcardSet, FlashcardSet.id == FlashcardCard.flashcard_set_id)
        .where(
            FlashcardCard.id == card_id,
            FlashcardSet.created_by == user.id,
            FlashcardSet.deleted_at.is_(None),
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    set_id = card.flashcard_set_id
    await db.delete(card)

    remaining = await db.execute(
        select(FlashcardCard)
        .where(FlashcardCard.flashcard_set_id == set_id)
        .order_by(FlashcardCard.card_index)
    )
    for idx, c in enumerate(remaining.scalars().all()):
        c.card_index = idx

    await db.commit()
    return APIResponse(success=True, data=None)


@router.patch(
    "/flashcard-cards/{card_id}",
    response_model=APIResponse[FlashcardCardResponse],
)
async def update_flashcard_card(
    card_id: uuid.UUID,
    body: FlashcardCardUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(FlashcardCard)
        .join(FlashcardSet, FlashcardSet.id == FlashcardCard.flashcard_set_id)
        .where(
            FlashcardCard.id == card_id,
            FlashcardSet.created_by == user.id,
            FlashcardSet.deleted_at.is_(None),
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    if body.front is not None:
        front = body.front.strip()
        if not front:
            raise HTTPException(status_code=400, detail="Front cannot be empty")
        card.front = front[:500]
    if body.back is not None:
        back = body.back.strip()
        if not back:
            raise HTTPException(status_code=400, detail="Back cannot be empty")
        card.back = back[:2000]
    if body.difficulty is not None:
        card.difficulty = body.difficulty

    await db.commit()
    await db.refresh(card)
    return APIResponse(
        success=True, data=FlashcardCardResponse.model_validate(card)
    )


@router.post(
    "/flashcard-cards/{card_id}/regenerate",
    response_model=APIResponse[FlashcardCardResponse],
)
async def regenerate_flashcard_card(
    card_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    from app.models.course import Course
    from app.services.embedder import embed_query
    from app.services.generator import generate_flashcards
    from app.services.retriever import retrieve_chunks

    result = await db.execute(
        select(FlashcardCard)
        .join(FlashcardSet, FlashcardSet.id == FlashcardCard.flashcard_set_id)
        .where(
            FlashcardCard.id == card_id,
            FlashcardSet.created_by == user.id,
            FlashcardSet.deleted_at.is_(None),
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    fc_set_result = await db.execute(
        select(FlashcardSet)
        .options(selectinload(FlashcardSet.source_documents))
        .where(FlashcardSet.id == card.flashcard_set_id)
    )
    fc_set = fc_set_result.scalar_one()

    course_result = await db.execute(
        select(Course).where(Course.id == fc_set.course_id)
    )
    course = course_result.scalar_one()

    doc_ids = [sd.document_id for sd in fc_set.source_documents] or None

    query_embedding = await embed_query(card.front)
    chunks = await retrieve_chunks(
        db,
        course_id=fc_set.course_id,
        query_embedding=query_embedding,
        top_k=10,
        document_ids=doc_ids,
    )

    generated = await generate_flashcards(
        chunks,
        num_cards=1,
        language=course.language,
        difficulty=card.difficulty or "medium",
    )
    if not generated:
        raise HTTPException(status_code=500, detail="Failed to regenerate card")

    new_card = generated[0]
    card.front = new_card.front
    card.back = new_card.back

    await db.commit()
    await db.refresh(card)
    return APIResponse(
        success=True, data=FlashcardCardResponse.model_validate(card)
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


async def _fc_folder_first_live_ancestor(
    db: AsyncSession, folder: FlashcardFolder
) -> uuid.UUID | None:
    """Walk up ancestors, returning the first non-deleted ancestor id or None (root)."""
    current = folder.parent_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if current in visited:
            logger.warning(
                "flashcard folder cycle detected during ancestor walk",
                extra={"folder_id": str(folder.id), "cycle_at": str(current)},
            )
            return None
        visited.add(current)
        ancestor = await db.get(FlashcardFolder, current)
        if ancestor is None:
            return None
        if ancestor.deleted_at is None:
            return ancestor.id
        current = ancestor.parent_id
    return None


async def _fc_folder_descendant_ids(
    db: AsyncSession, root_id: uuid.UUID
) -> set[uuid.UUID]:
    """Return all descendant folder ids of ``root_id`` (inclusive) via a recursive CTE."""
    base = (
        select(FlashcardFolder.id.label("id"))
        .where(
            FlashcardFolder.id == root_id,
            FlashcardFolder.deleted_at.is_(None),
        )
        .cte(name="flashcard_folder_descendants", recursive=True)
    )
    recursive = select(FlashcardFolder.id).where(
        FlashcardFolder.parent_id == base.c.id,
        FlashcardFolder.deleted_at.is_(None),
    )
    cte = base.union_all(recursive)
    rows = (await db.execute(select(cte.c.id))).scalars().all()
    return set(rows)


async def _fc_folder_subtree_height(
    db: AsyncSession, folder_id: uuid.UUID
) -> int:
    """Return the height of the subtree rooted at ``folder_id``.

    Height is the max number of edges from ``folder_id`` down to a descendant
    leaf. 0 when there are no live children.
    """
    height = 0
    frontier: set[uuid.UUID] = {folder_id}
    visited: set[uuid.UUID] = {folder_id}
    while frontier:
        rows = (
            await db.execute(
                select(FlashcardFolder.id).where(
                    FlashcardFolder.parent_id.in_(frontier),
                    FlashcardFolder.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        next_frontier: set[uuid.UUID] = set()
        for child_id in rows:
            if child_id in visited:
                continue
            visited.add(child_id)
            next_frontier.add(child_id)
        if not next_frontier:
            break
        height += 1
        frontier = next_frontier
        if height > MAX_FOLDER_DEPTH:
            return height
    return height


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
    # Hoisted auth check — verify enrollment before taking row locks.
    preview = await db.get(FlashcardFolder, folder_id)
    if preview is None or preview.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, preview.course_id, user.id)
    await db.rollback()

    # Serialize the move under SERIALIZABLE isolation with row-level locks on
    # the two endpoints; sort lock IDs by UUID bytes to prevent deadlock
    # against a concurrent swapped move. SERIALIZABLE covers the
    # ancestor-chain reads that aren't explicitly locked.
    candidate_ids = {folder_id}
    if body.parent_id is not None and body.parent_id != folder_id:
        candidate_ids.add(body.parent_id)
    lock_ids: list[uuid.UUID] = sorted(candidate_ids, key=lambda x: x.bytes)

    folder: FlashcardFolder | None = None
    for attempt in range(3):
        try:
            await db.connection(
                execution_options={"isolation_level": "SERIALIZABLE"}
            )
            locked_rows = (
                await db.execute(
                    select(FlashcardFolder)
                    .where(FlashcardFolder.id.in_(lock_ids))
                    .order_by(FlashcardFolder.id)
                    .with_for_update()
                )
            ).scalars().all()
            locked_by_id = {row.id: row for row in locked_rows}

            folder = locked_by_id.get(folder_id)
            if folder is None or folder.deleted_at is not None:
                raise HTTPException(status_code=404, detail="Folder not found")
            if body.parent_id is not None:
                if body.parent_id == folder_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot nest folder inside itself",
                    )
                parent = locked_by_id.get(body.parent_id)
                if (
                    parent is None
                    or parent.deleted_at is not None
                    or parent.course_id != folder.course_id
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Parent folder not found in this course",
                    )
                descendants = await _fc_folder_descendant_ids(db, folder_id)
                if body.parent_id in descendants:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot move folder into its own descendant",
                    )
                parent_depth = await _fc_folder_ancestor_depth(db, parent.id)
                subtree_height = await _fc_folder_subtree_height(db, folder_id)
                if parent_depth + subtree_height > MAX_FOLDER_DEPTH:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Folder nesting exceeds maximum depth of {MAX_FOLDER_DEPTH}",
                    )
                # Note: FlashcardFolder has no `purpose` column today, so no
                # purpose-equality check is enforced here. Intentional
                # asymmetry with QuizFolder pending schema evolution.
            folder.parent_id = body.parent_id
            await db.commit()
            break
        except DBAPIError as exc:
            pgcode = getattr(exc.orig, "pgcode", None) if exc.orig else None
            if pgcode in ("40001", "40P01") and attempt < 2:
                await db.rollback()
                await asyncio.sleep(0.05 * (2**attempt))
                continue
            if pgcode in ("40001", "40P01"):
                await db.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="conflicting_move_please_retry",
                ) from exc
            raise

    assert folder is not None
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

    # Reparent to the nearest live ancestor, walking up the chain so children
    # don't end up orphaned under a soft-deleted grandparent.
    new_parent = await _fc_folder_first_live_ancestor(db, folder)

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
