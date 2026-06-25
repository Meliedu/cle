import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.learning_events import record_attempt_event

logger = logging.getLogger(__name__)

from app.api._helpers import verify_enrollment
from app.api.deps import get_current_user, get_db, require_student
from app.models.revision import (
    BanditModel,
    RevisionAttempt,
    RevisionItemServed,
    RevisionPoolItem,
    RevisionSession,
)
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.revision import (
    EndSessionResponse,
    RevisionFlashcardItem,
    RevisionItem,
    RevisionQuizItem,
    RevisionSpeakingItem,
    SessionStats,
    StartRevisionRequest,
    StartRevisionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.services.bandit import (
    COLD_START_THRESHOLD,
    DIFFICULTY_TO_IDX,
    compute_state_vector,
    create_initial_weights,
    select_difficulty,
    update_policy,
)
from app.services.recalibrator import accumulate_stats, maybe_trigger_recalibration

router = APIRouter(tags=["revision"])

POOL_MIN_PER_DIFFICULTY = 5
FLASHCARD_QUALITY_TO_SCORE = {0: 0.0, 1: 0.2, 2: 0.4, 3: 0.7, 4: 0.85, 5: 1.0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _verify_session_owner(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> RevisionSession:
    result = await db.execute(
        select(RevisionSession).where(
            RevisionSession.id == session_id,
            RevisionSession.user_id == user_id,
            RevisionSession.ended_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or ended")
    return session


async def _get_unserved_counts(
    db: AsyncSession, course_id: uuid.UUID, content_type: str, user_id: uuid.UUID
) -> dict[str, int]:
    """Count unserved pool items per difficulty for this user."""
    effective_difficulty = func.coalesce(
        RevisionPoolItem.recalibrated_difficulty, RevisionPoolItem.difficulty
    )
    stmt = (
        select(
            effective_difficulty,
            func.count(RevisionPoolItem.id),
        )
        .outerjoin(
            RevisionItemServed,
            (RevisionItemServed.pool_item_id == RevisionPoolItem.id)
            & (RevisionItemServed.user_id == user_id),
        )
        .where(
            RevisionPoolItem.course_id == course_id,
            RevisionPoolItem.content_type == content_type,
            RevisionItemServed.user_id.is_(None),  # not served
        )
        .group_by(effective_difficulty)
    )
    result = await db.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


async def _enqueue_replenish(
    db: AsyncSession, course_id: uuid.UUID, content_type: str
) -> None:
    task = Task(
        task_type="revision_pool_replenish",
        payload={
            "course_id": str(course_id),
            "content_type": content_type,
            "counts": {"easy": 7, "medium": 7, "hard": 6},
        },
    )
    db.add(task)
    await db.flush()


def _enqueue_mastery_for_revision(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    pool_item_id: uuid.UUID,
    score: float,
) -> None:
    """Add a single ``update_concept_mastery`` Task row for a revision attempt.

    ``score`` is already in [0, 1] from the per-content-type score logic in
    ``submit_answer`` (quiz: 1/0, flashcard: SM-2 quality bucket, speaking:
    overall_score / 100). Caller commits.
    """
    outcome = max(0.0, min(1.0, float(score)))
    db.add(
        Task(
            task_type="update_concept_mastery",
            payload={
                "user_id": str(user_id),
                "course_id": str(course_id),
                "target_kind": "pool_item",
                "target_id": str(pool_item_id),
                "outcome": outcome,
                "attempt_kind": "revision",
            },
            status="pending",
        )
    )


async def _pick_item(
    db: AsyncSession,
    course_id: uuid.UUID,
    content_type: str,
    difficulty: str,
    user_id: uuid.UUID,
) -> RevisionPoolItem | None:
    """Pick a random unserved pool item at the given difficulty."""
    stmt = (
        select(RevisionPoolItem)
        .outerjoin(
            RevisionItemServed,
            (RevisionItemServed.pool_item_id == RevisionPoolItem.id)
            & (RevisionItemServed.user_id == user_id),
        )
        .where(
            RevisionPoolItem.course_id == course_id,
            RevisionPoolItem.content_type == content_type,
            func.coalesce(RevisionPoolItem.recalibrated_difficulty, RevisionPoolItem.difficulty) == difficulty,
            RevisionItemServed.user_id.is_(None),
        )
        .order_by(func.random())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _pick_item_any_difficulty(
    db: AsyncSession,
    course_id: uuid.UUID,
    content_type: str,
    user_id: uuid.UUID,
) -> RevisionPoolItem | None:
    """Fallback: pick any unserved item regardless of difficulty."""
    stmt = (
        select(RevisionPoolItem)
        .outerjoin(
            RevisionItemServed,
            (RevisionItemServed.pool_item_id == RevisionPoolItem.id)
            & (RevisionItemServed.user_id == user_id),
        )
        .where(
            RevisionPoolItem.course_id == course_id,
            RevisionPoolItem.content_type == content_type,
            RevisionItemServed.user_id.is_(None),
        )
        .order_by(func.random())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _pool_item_to_response(item: RevisionPoolItem) -> RevisionItem:
    if item.content_type == "quiz":
        return RevisionQuizItem(
            pool_item_id=str(item.id),
            question_text=item.question_text,
            options=item.options,
        )
    elif item.content_type == "flashcard":
        return RevisionFlashcardItem(
            pool_item_id=str(item.id),
            front=item.front,
            back=item.back,
        )
    else:
        return RevisionSpeakingItem(
            pool_item_id=str(item.id),
            target_text=item.target_text,
            language=item.language or "english",
        )


async def _get_recent_attempts(
    db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID, content_type: str, limit: int = 50
) -> list[SimpleNamespace]:
    """Return recent attempts as SimpleNamespace objects for attribute access."""
    stmt = (
        select(RevisionAttempt)
        .where(
            RevisionAttempt.user_id == user_id,
            RevisionAttempt.course_id == course_id,
            RevisionAttempt.content_type == content_type,
        )
        .order_by(RevisionAttempt.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    rows.reverse()  # most-recent-last so attempts[-1] is the latest
    return [
        SimpleNamespace(
            difficulty=a.corrected_difficulty or a.difficulty,
            corrected_difficulty=a.corrected_difficulty,
            score=float(a.score),
            created_at=a.created_at,
        )
        for a in rows
    ]


async def _get_bandit_model(
    db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID, content_type: str
) -> BanditModel | None:
    stmt = select(BanditModel).where(
        BanditModel.user_id == user_id,
        BanditModel.course_id == course_id,
        BanditModel.content_type == content_type,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _select_and_serve(
    db: AsyncSession, session: RevisionSession, user: User
) -> RevisionItem | None:
    """Run bandit selection and pick an item. Returns None if pool is empty."""
    attempts = await _get_recent_attempts(
        db, user.id, session.course_id, session.content_type
    )
    bandit_model = await _get_bandit_model(
        db, user.id, session.course_id, session.content_type
    )

    state = compute_state_vector(attempts, current_session_count=session.items_answered)
    recent_diffs = [a.difficulty for a in attempts[-5:]]

    difficulty, _ = select_difficulty(
        state=state,
        weights=bandit_model.weights if bandit_model else None,
        attempt_count=bandit_model.attempt_count if bandit_model else 0,
        recent_history=attempts[-5:],
        recent_difficulties=recent_diffs,
    )

    item = await _pick_item(db, session.course_id, session.content_type, difficulty, user.id)
    if item is None:
        item = await _pick_item_any_difficulty(db, session.course_id, session.content_type, user.id)

    if item is None:
        return None

    # Mark as served
    db.add(RevisionItemServed(user_id=user.id, pool_item_id=item.id))
    await db.flush()

    # Check pool levels, trigger replenishment if needed
    counts = await _get_unserved_counts(db, session.course_id, session.content_type, user.id)
    for diff in ["easy", "medium", "hard"]:
        if counts.get(diff, 0) < POOL_MIN_PER_DIFFICULTY:
            await _enqueue_replenish(db, session.course_id, session.content_type)
            break

    return _pool_item_to_response(item)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/courses/{course_id}/revision/start",
    response_model=APIResponse[StartRevisionResponse],
    status_code=201,
)
async def start_revision(
    course_id: uuid.UUID,
    body: StartRevisionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
):
    await verify_enrollment(db, course_id, user.id)

    session = RevisionSession(
        user_id=user.id,
        course_id=course_id,
        content_type=body.content_type,
    )
    db.add(session)
    await db.flush()

    # Check pool
    counts = await _get_unserved_counts(db, course_id, body.content_type, user.id)
    total_available = sum(counts.values())

    if total_available < 3:
        # Pool empty -- enqueue generation and return preparing
        await _enqueue_replenish(db, course_id, body.content_type)
        await db.commit()
        return APIResponse(
            success=True,
            data=StartRevisionResponse(
                session_id=str(session.id),
                status="preparing",
                first_item=None,
            ),
        )

    first_item = await _select_and_serve(db, session, user)
    await db.commit()

    return APIResponse(
        success=True,
        data=StartRevisionResponse(
            session_id=str(session.id),
            status="ready",
            first_item=first_item,
        ),
    )


@router.post(
    "/revision/sessions/{session_id}/answer",
    response_model=APIResponse[SubmitAnswerResponse],
)
async def submit_answer(
    session_id: uuid.UUID,
    body: SubmitAnswerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
):
    session = await _verify_session_owner(db, session_id, user.id)

    # Fetch the pool item, scoped to the session's course to prevent IDOR.
    item_result = await db.execute(
        select(RevisionPoolItem).where(
            RevisionPoolItem.id == body.pool_item_id,
            RevisionPoolItem.course_id == session.course_id,
        )
    )
    pool_item = item_result.scalar_one_or_none()
    if not pool_item:
        raise HTTPException(status_code=404, detail="Pool item not found")

    # Score the answer
    is_correct = None
    correct_answer = None
    explanation = None

    if pool_item.content_type == "quiz":
        is_correct = body.answer == pool_item.correct_answer
        score = 1.0 if is_correct else 0.0
        correct_answer = pool_item.correct_answer
        explanation = pool_item.explanation
    elif pool_item.content_type == "flashcard":
        quality = body.quality if body.quality is not None else 3
        score = FLASHCARD_QUALITY_TO_SCORE.get(quality, 0.7)
    elif pool_item.content_type == "speaking":
        score = (body.pronunciation_score or 0.0) / 100.0
    else:
        score = 0.0

    # Record attempt
    attempt = RevisionAttempt(
        user_id=user.id,
        course_id=session.course_id,
        session_id=session.id,
        pool_item_id=pool_item.id,
        content_type=pool_item.content_type,
        difficulty=pool_item.difficulty,
        score=Decimal(str(round(score, 2))),
        time_taken_ms=body.time_taken_ms,
    )
    db.add(attempt)

    # Recalibration stat accumulation
    await accumulate_stats(
        db,
        pool_item_id=pool_item.id,
        course_id=session.course_id,
        content_type=pool_item.content_type,
        llm_difficulty=pool_item.difficulty,
        score=score,
    )
    await maybe_trigger_recalibration(db, session.course_id, pool_item.content_type)

    # Update session counters
    session.items_answered = (session.items_answered or 0) + 1
    session.total_score = (session.total_score or Decimal("0")) + Decimal(str(round(score, 2)))

    # Bandit update
    bandit_model = await _get_bandit_model(db, user.id, session.course_id, session.content_type)
    if bandit_model is None:
        bandit_model = BanditModel(
            user_id=user.id,
            course_id=session.course_id,
            content_type=session.content_type,
            weights=create_initial_weights(),
        )
        db.add(bandit_model)
        await db.flush()

    bandit_model.attempt_count = (bandit_model.attempt_count or 0) + 1

    # Update running reward stats
    old_mean = bandit_model.reward_mean or 0.0
    old_var = bandit_model.reward_var or 1.0
    new_mean = 0.99 * old_mean + 0.01 * score
    new_var = 0.99 * old_var + 0.01 * (score - new_mean) ** 2
    bandit_model.reward_mean = new_mean
    bandit_model.reward_var = new_var

    # REINFORCE update (only if past cold start)
    if bandit_model.attempt_count >= COLD_START_THRESHOLD and bandit_model.strategy != "rules":
        attempts = await _get_recent_attempts(
            db, user.id, session.course_id, session.content_type
        )
        state = compute_state_vector(attempts, current_session_count=session.items_answered)

        new_weights, updated_mean, updated_var = update_policy(
            weights=bandit_model.weights,
            state=state,
            chosen_idx=DIFFICULTY_TO_IDX[pool_item.recalibrated_difficulty or pool_item.difficulty],
            reward=score,
            reward_mean=old_mean,
            reward_var=old_var,
            use_normalized_reward=True,
        )
        bandit_model.weights = new_weights
        bandit_model.reward_mean = updated_mean
        bandit_model.reward_var = updated_var

    # Auto-transition from rules to bandit
    if (
        bandit_model.attempt_count >= COLD_START_THRESHOLD
        and bandit_model.strategy == "rules"
    ):
        bandit_model.strategy = "bandit"

    # Select next item
    next_item = await _select_and_serve(db, session, user)

    await db.commit()

    # Enqueue mastery update after attempt is durable. Failure here must not
    # roll back the student's attempt; we log and swallow.
    try:
        _enqueue_mastery_for_revision(
            db,
            user_id=user.id,
            course_id=session.course_id,
            pool_item_id=pool_item.id,
            score=score,
        )
        await record_attempt_event(
            db,
            course_id=session.course_id,
            user_id=user.id,
            source_kind="revision",
            source_id=pool_item.id,
            stage="review",
            value={"score": score},
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — non-fatal: attempt already persisted
        logger.exception(
            "Failed to enqueue mastery update for pool_item_id=%s user_id=%s",
            pool_item.id,
            user.id,
        )
        await db.rollback()

    # Compute session stats
    avg_score = float(session.total_score) / session.items_answered if session.items_answered > 0 else 0.0

    # Compute current streak
    recent = await _get_recent_attempts(db, user.id, session.course_id, session.content_type, limit=50)
    streak = 0
    for a in reversed(recent):
        if a.score >= 0.8:
            streak += 1
        else:
            break

    return APIResponse(
        success=True,
        data=SubmitAnswerResponse(
            score=score,
            is_correct=is_correct,
            correct_answer=correct_answer,
            explanation=explanation,
            next_item=next_item,
            session_stats=SessionStats(
                items_answered=session.items_answered,
                accuracy=round(avg_score, 3),
                current_streak=streak,
            ),
        ),
    )


@router.post(
    "/revision/sessions/{session_id}/next",
    response_model=APIResponse[RevisionItem | None],
)
async def next_item(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
):
    session = await _verify_session_owner(db, session_id, user.id)
    item = await _select_and_serve(db, session, user)
    await db.commit()
    return APIResponse(success=True, data=item)


@router.get(
    "/revision/sessions/{session_id}",
    response_model=APIResponse[SessionStats],
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
):
    session = await _verify_session_owner(db, session_id, user.id)
    avg = float(session.total_score) / session.items_answered if session.items_answered > 0 else 0.0

    recent = await _get_recent_attempts(db, user.id, session.course_id, session.content_type, limit=50)
    streak = 0
    for a in reversed(recent):
        if a.score >= 0.8:
            streak += 1
        else:
            break

    return APIResponse(
        success=True,
        data=SessionStats(
            items_answered=session.items_answered,
            accuracy=round(avg, 3),
            current_streak=streak,
        ),
    )


@router.post(
    "/revision/sessions/{session_id}/end",
    response_model=APIResponse[EndSessionResponse],
)
async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
):
    result = await db.execute(
        select(RevisionSession).where(
            RevisionSession.id == session_id,
            RevisionSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.ended_at = datetime.now(timezone.utc)

    # Compute scores by difficulty
    stmt = (
        select(
            RevisionAttempt.difficulty,
            func.avg(RevisionAttempt.score),
        )
        .where(RevisionAttempt.session_id == session_id)
        .group_by(RevisionAttempt.difficulty)
    )
    diff_result = await db.execute(stmt)
    scores_by_diff = {row[0]: round(float(row[1]), 3) for row in diff_result.all()}

    avg = float(session.total_score) / session.items_answered if session.items_answered > 0 else 0.0
    duration = int((session.ended_at - session.started_at).total_seconds()) if session.started_at else 0

    await db.commit()

    return APIResponse(
        success=True,
        data=EndSessionResponse(
            items_answered=session.items_answered,
            average_score=round(avg, 3),
            scores_by_difficulty=scores_by_diff,
            duration_seconds=duration,
        ),
    )
