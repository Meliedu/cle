"""Bayesian difficulty recalibrator.

Uses Dirichlet-Multinomial conjugate priors to model the transition
between LLM-assigned difficulty labels and observed student performance,
then applies Beta-Binomial posteriors per item to decide whether an
item's difficulty label should be changed.

Pure-math helpers are defined first (no DB), followed by DB-facing
functions at the bottom of the file.
"""

from __future__ import annotations

import copy
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIFFICULTIES: list[str] = ["easy", "medium", "hard"]
DIFFICULTY_ORDER: dict[str, int] = {"easy": 0, "medium": 1, "hard": 2}

DIRICHLET_PRIOR_STRONG: float = 10.0
DIRICHLET_PRIOR_WEAK: float = 1.0
EQUIVALENT_SAMPLE_SIZE: float = 5.0

MIN_ATTEMPTS_FOR_LAYER1: int = 5
DOWNGRADE_THRESHOLD: float = 0.90
UPGRADE_THRESHOLD: float = 0.95

EASY_SCORE_THRESHOLD: float = 0.85
HARD_SCORE_THRESHOLD: float = 0.45

BATCH_TRIGGER_ATTEMPTS: int = 50


# ---------------------------------------------------------------------------
# Dirichlet prior helpers
# ---------------------------------------------------------------------------


def build_initial_dirichlet() -> dict[str, dict[str, float]]:
    """Build the initial Dirichlet parameters for the confusion matrix.

    Strong prior on the diagonal (LLM label matches observed difficulty),
    weak prior off-diagonal.
    """
    return {
        row: {
            col: DIRICHLET_PRIOR_STRONG if row == col else DIRICHLET_PRIOR_WEAK
            for col in DIFFICULTIES
        }
        for row in DIFFICULTIES
    }


def compute_transition_matrix(
    dirichlet_params: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Normalize Dirichlet parameters to get a row-stochastic transition matrix."""
    matrix: dict[str, dict[str, float]] = {}
    for row in DIFFICULTIES:
        row_total = sum(dirichlet_params[row][col] for col in DIFFICULTIES)
        matrix[row] = {
            col: dirichlet_params[row][col] / row_total for col in DIFFICULTIES
        }
    return matrix


# ---------------------------------------------------------------------------
# Observed difficulty classification
# ---------------------------------------------------------------------------


def classify_observed_difficulty(mean_score: float) -> str:
    """Classify an item's observed difficulty from its mean student score.

    >= EASY_SCORE_THRESHOLD  (0.85) → easy
    <  HARD_SCORE_THRESHOLD  (0.45) → hard
    otherwise                       → medium
    """
    if mean_score >= EASY_SCORE_THRESHOLD:
        return "easy"
    if mean_score < HARD_SCORE_THRESHOLD:
        return "hard"
    return "medium"


# ---------------------------------------------------------------------------
# Dirichlet update
# ---------------------------------------------------------------------------


def update_dirichlet(
    params: dict[str, dict[str, float]],
    llm_difficulty: str,
    observed_difficulty: str,
) -> dict[str, dict[str, float]]:
    """Return new Dirichlet params with one observation added.

    Deep-copies to preserve immutability.
    """
    new_params = copy.deepcopy(params)
    new_params[llm_difficulty][observed_difficulty] += 1
    return new_params


# ---------------------------------------------------------------------------
# Item-level posterior
# ---------------------------------------------------------------------------


def compute_item_posterior(
    llm_difficulty: str,
    transition_matrix: dict[str, dict[str, float]],
    correct_count: int,
    hard_count: int,
    attempt_count: int,
) -> dict[str, float]:
    """Compute Beta-posterior probability for each true difficulty.

    Uses the course-level transition matrix row as a prior, scaled
    by EQUIVALENT_SAMPLE_SIZE (k).

    Parameters
    ----------
    llm_difficulty : str
        The LLM-assigned label for this item.
    transition_matrix : dict
        Course-level Dirichlet-derived transition matrix.
    correct_count : int
        Number of "easy-signal" attempts (high scores).
    hard_count : int
        Number of "hard-signal" attempts (low scores).
    attempt_count : int
        Total attempts on this item.

    Returns
    -------
    dict[str, float]
        Posterior mean for each difficulty category.
    """
    prior_row = transition_matrix[llm_difficulty]
    k = EQUIVALENT_SAMPLE_SIZE
    medium_count = attempt_count - correct_count - hard_count

    # Beta parameters for "easy"
    alpha_easy = prior_row["easy"] * k + correct_count
    beta_easy = (1 - prior_row["easy"]) * k + hard_count

    # Beta parameters for "medium"
    alpha_medium = prior_row["medium"] * k + medium_count
    beta_medium = (1 - prior_row["medium"]) * k + (correct_count + hard_count)

    # Beta parameters for "hard"
    alpha_hard = prior_row["hard"] * k + hard_count
    beta_hard = (1 - prior_row["hard"]) * k + correct_count

    posterior: dict[str, float] = {}
    for label, alpha, beta in [
        ("easy", alpha_easy, beta_easy),
        ("medium", alpha_medium, beta_medium),
        ("hard", alpha_hard, beta_hard),
    ]:
        posterior[label] = alpha / (alpha + beta)

    return posterior


# ---------------------------------------------------------------------------
# Relabel decision
# ---------------------------------------------------------------------------


def make_relabel_decision(
    llm_difficulty: str,
    posterior: dict[str, float],
) -> tuple[str, float] | None:
    """Decide whether to relabel an item based on its posterior.

    Uses asymmetric thresholds:
    - Downgrade (easier than LLM label): DOWNGRADE_THRESHOLD (0.90)
    - Upgrade   (harder than LLM label): UPGRADE_THRESHOLD   (0.95)

    Returns (new_label, confidence) or None if no relabel warranted.
    """
    best = max(posterior, key=lambda d: posterior[d])
    confidence = posterior[best]

    if best == llm_difficulty:
        return None

    # Determine direction: downgrade means the best label is easier
    if DIFFICULTY_ORDER[best] < DIFFICULTY_ORDER[llm_difficulty]:
        threshold = DOWNGRADE_THRESHOLD
    else:
        threshold = UPGRADE_THRESHOLD

    if confidence >= threshold:
        return (best, confidence)

    return None


# ---------------------------------------------------------------------------
# Batch recalibration pipeline
# ---------------------------------------------------------------------------


def run_recalibration_pure(
    stats_list: list[Any],
    dirichlet_params: dict[str, dict[str, float]],
) -> tuple[
    dict[str, dict[str, float]],        # updated dirichlet
    list[tuple[str, str, float]],        # relabels: (pool_item_id, new_diff, confidence)
    list[str],                           # reverts: pool_item_ids to revert
]:
    """Orchestrate Layer 1 + Layer 2 recalibration over a list of item stats.

    Parameters
    ----------
    stats_list : list
        Each element must expose: pool_item_id, llm_difficulty, attempt_count,
        correct_count, hard_count, score_sum, instructor_override.
    dirichlet_params : dict
        Starting Dirichlet parameters (typically from build_initial_dirichlet()).
        This function always resets to initial priors for idempotency, so the
        caller's value is used only to determine the prior shape.

    Returns
    -------
    updated_dirichlet : dict
        Dirichlet params after accumulating qualifying observations.
    relabels : list of (pool_item_id, new_difficulty, confidence)
        Items whose label should change.
    reverts : list of pool_item_id
        Items whose label should revert to the LLM original (no relabel warranted).
    """
    # Step 1 — reset to initial priors for idempotency
    updated_dirichlet = build_initial_dirichlet()

    # Step 2 — accumulate qualifying observations into Dirichlet
    for stats in stats_list:
        if stats.instructor_override:
            continue
        if stats.attempt_count < MIN_ATTEMPTS_FOR_LAYER1:
            continue
        mean_score = stats.score_sum / stats.attempt_count
        observed = classify_observed_difficulty(mean_score)
        updated_dirichlet = update_dirichlet(
            updated_dirichlet, stats.llm_difficulty, observed
        )

    # Step 3 — derive transition matrix from updated Dirichlet
    transition_matrix = compute_transition_matrix(updated_dirichlet)

    # Step 4 — item-level posterior and relabel decisions
    relabels: list[tuple[str, str, float]] = []
    reverts: list[str] = []

    for stats in stats_list:
        if stats.instructor_override:
            continue
        posterior = compute_item_posterior(
            stats.llm_difficulty,
            transition_matrix,
            stats.correct_count,
            stats.hard_count,
            stats.attempt_count,
        )
        decision = make_relabel_decision(stats.llm_difficulty, posterior)
        if decision is not None:
            new_diff, confidence = decision
            relabels.append((stats.pool_item_id, new_diff, confidence))
        else:
            reverts.append(stats.pool_item_id)

    return updated_dirichlet, relabels, reverts


# ---------------------------------------------------------------------------
# DB-facing functions
# ---------------------------------------------------------------------------


async def accumulate_stats(
    db: "AsyncSession",
    pool_item_id: "UUID",
    course_id: "UUID",
    content_type: str,
    llm_difficulty: str,
    score: float,
) -> None:
    """Upsert per-item recalibration stats. Called from the /answer hot path.

    IMPORTANT — ``llm_difficulty`` contract:
        This value MUST be the ORIGINAL LLM-assigned difficulty label for the pool
        item (i.e., ``RevisionPoolItem.llm_difficulty``), NOT the recalibrated /
        corrected label. The Dirichlet confusion matrix models
        P(observed | LLM-label); passing a recalibrated label would feed the
        matrix its own output back as input, poisoning the prior and causing
        the recalibrator to converge to a degenerate fixed point over time.
    """
    from uuid import UUID as _UUID  # noqa: F811
    from sqlalchemy.dialects.postgresql import insert
    from app.models.recalibration import RecalibrationStats

    stmt = (
        insert(RecalibrationStats)
        .values(
            pool_item_id=pool_item_id,
            course_id=course_id,
            content_type=content_type,
            llm_difficulty=llm_difficulty,
            attempt_count=1,
            correct_count=1 if score >= 0.8 else 0,
            hard_count=1 if score < 0.4 else 0,
            score_sum=score,
            score_sq_sum=score * score,
        )
        .on_conflict_do_update(
            index_elements=["pool_item_id"],
            set_={
                "attempt_count": RecalibrationStats.attempt_count + 1,
                "correct_count": RecalibrationStats.correct_count + (1 if score >= 0.8 else 0),
                "hard_count": RecalibrationStats.hard_count + (1 if score < 0.4 else 0),
                "score_sum": RecalibrationStats.score_sum + score,
                "score_sq_sum": RecalibrationStats.score_sq_sum + (score * score),
            },
        )
    )
    await db.execute(stmt)


async def maybe_trigger_recalibration(
    db: "AsyncSession",
    course_id: "UUID",
    content_type: str,
) -> None:
    """Check attempt counter and enqueue a recalibration task if threshold reached.

    Uses a server-side atomic UPDATE to increment ``total_attempts_since_last_run``
    so concurrent /answer requests cannot read the same stale counter and produce
    a lost-update.
    """
    from sqlalchemy import func, select, update
    from app.models.recalibration import RecalibrationModel, RecalibrationStats
    from app.models.task import Task

    result = await db.execute(
        select(RecalibrationModel.id).where(
            RecalibrationModel.course_id == course_id,
            RecalibrationModel.content_type == content_type,
        )
    )
    model_id = result.scalar_one_or_none()

    if model_id is None:
        # Bootstrap a model row so future calls hit the cheap atomic-increment
        # path instead of re-summing recalibration_stats every request.
        sum_result = await db.execute(
            select(func.coalesce(func.sum(RecalibrationStats.attempt_count), 0)).where(
                RecalibrationStats.course_id == course_id,
                RecalibrationStats.content_type == content_type,
            )
        )
        total = int(sum_result.scalar_one() or 0)
        db.add(
            RecalibrationModel(
                course_id=course_id,
                content_type=content_type,
                dirichlet_params=build_initial_dirichlet(),
                transition_matrix=compute_transition_matrix(build_initial_dirichlet()),
                items_used=0,
                total_attempts_since_last_run=total,
            )
        )
    else:
        upd = (
            update(RecalibrationModel)
            .where(RecalibrationModel.id == model_id)
            .values(
                total_attempts_since_last_run=(
                    RecalibrationModel.total_attempts_since_last_run + 1
                )
            )
            .returning(RecalibrationModel.total_attempts_since_last_run)
        )
        total = (await db.execute(upd)).scalar_one()

    if total >= BATCH_TRIGGER_ATTEMPTS:
        # Dedup: skip enqueue if a pending/running recalibration task already
        # exists for this (course_id, content_type). Without this guard, each
        # /answer call between enqueue and worker completion would re-enqueue,
        # producing spam when no model exists yet (the total is recomputed from
        # the stats sum each call instead of decremented).
        existing_task_result = await db.execute(
            select(Task).where(
                Task.task_type == "recalibration",
                Task.status.in_(["pending", "running"]),
                Task.payload["course_id"].astext == str(course_id),
                Task.payload["content_type"].astext == content_type,
            )
        )
        if existing_task_result.scalar_one_or_none() is not None:
            return

        # Race condition note: concurrent requests may each enqueue a
        # recalibration task before the counter resets.  This is harmless
        # because run_recalibration_job is idempotent — duplicate tasks
        # simply recompute the same Dirichlet posteriors and produce
        # identical relabel decisions.
        task = Task(
            task_type="recalibration",
            payload={
                "course_id": str(course_id),
                "content_type": content_type,
            },
        )
        db.add(task)


async def run_recalibration_job(
    db: "AsyncSession",
    course_id: "UUID",
    content_type: str,
) -> dict[str, int]:
    """Full batch recalibration job, called by the worker."""
    import logging
    from types import SimpleNamespace
    from uuid import UUID

    from sqlalchemy import select, update
    from app.models.recalibration import RecalibrationModel, RecalibrationStats
    from app.models.revision import RevisionAttempt, RevisionPoolItem

    logger = logging.getLogger(__name__)

    # 1. Load stats joined with override flag
    result = await db.execute(
        select(
            RecalibrationStats.pool_item_id,
            RecalibrationStats.llm_difficulty,
            RecalibrationStats.attempt_count,
            RecalibrationStats.correct_count,
            RecalibrationStats.hard_count,
            RecalibrationStats.score_sum,
            RevisionPoolItem.instructor_override,
        )
        .join(RevisionPoolItem, RecalibrationStats.pool_item_id == RevisionPoolItem.id)
        .where(
            RecalibrationStats.course_id == course_id,
            RecalibrationStats.content_type == content_type,
        )
    )
    rows = result.all()
    if not rows:
        return {"scanned": 0, "relabeled": 0, "reverted": 0}

    stats_list = [
        SimpleNamespace(
            pool_item_id=str(r.pool_item_id),
            llm_difficulty=r.llm_difficulty,
            attempt_count=r.attempt_count,
            correct_count=r.correct_count,
            hard_count=r.hard_count,
            score_sum=float(r.score_sum),
            instructor_override=r.instructor_override,
        )
        for r in rows
    ]

    # 2. Load existing model
    model_result = await db.execute(
        select(RecalibrationModel).where(
            RecalibrationModel.course_id == course_id,
            RecalibrationModel.content_type == content_type,
        )
    )
    existing_model = model_result.scalar_one_or_none()
    old_dirichlet = existing_model.dirichlet_params if existing_model else build_initial_dirichlet()

    # 3. Run pure logic
    new_dirichlet, relabels, reverts = run_recalibration_pure(stats_list, old_dirichlet)
    new_matrix = compute_transition_matrix(new_dirichlet)

    # 4. Persist model
    qualifying = len([s for s in stats_list if s.attempt_count >= MIN_ATTEMPTS_FOR_LAYER1])
    if existing_model:
        existing_model.dirichlet_params = new_dirichlet
        existing_model.transition_matrix = new_matrix
        existing_model.items_used = qualifying
        existing_model.total_attempts_since_last_run = 0
    else:
        db.add(RecalibrationModel(
            course_id=course_id,
            content_type=content_type,
            dirichlet_params=new_dirichlet,
            transition_matrix=new_matrix,
            items_used=qualifying,
            total_attempts_since_last_run=0,
        ))

    # 5. Apply relabels — bulk-update per (new_diff, rounded_confidence) group
    # to collapse N round-trips into at most a handful per content type.
    if relabels:
        from collections import defaultdict
        grouped: dict[tuple[str, float], list[UUID]] = defaultdict(list)
        for pool_item_id_str, new_diff, confidence in relabels:
            grouped[(new_diff, round(float(confidence), 3))].append(UUID(pool_item_id_str))

        for (new_diff, conf), pids in grouped.items():
            await db.execute(
                update(RevisionPoolItem)
                .where(RevisionPoolItem.id.in_(pids))
                .values(recalibrated_difficulty=new_diff, recalibration_confidence=conf)
            )
            await db.execute(
                update(RevisionAttempt)
                .where(
                    RevisionAttempt.pool_item_id.in_(pids),
                    RevisionAttempt.corrected_difficulty.is_(None),
                )
                .values(corrected_difficulty=new_diff)
            )

    # 6. Revert items no longer meeting threshold
    if reverts:
        revert_pids = [UUID(s) for s in reverts]
        await db.execute(
            update(RevisionPoolItem)
            .where(
                RevisionPoolItem.id.in_(revert_pids),
                RevisionPoolItem.recalibrated_difficulty.is_not(None),
            )
            .values(recalibrated_difficulty=None, recalibration_confidence=None)
        )
        await db.execute(
            update(RevisionAttempt)
            .where(
                RevisionAttempt.pool_item_id.in_(revert_pids),
                RevisionAttempt.corrected_difficulty.is_not(None),
            )
            .values(corrected_difficulty=None)
        )

    await db.flush()

    summary = {"scanned": len(stats_list), "relabeled": len(relabels), "reverted": len(reverts)}
    logger.info("Recalibration complete for course=%s content_type=%s: %s", course_id, content_type, summary)
    return summary
