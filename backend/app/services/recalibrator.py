"""Bayesian difficulty recalibrator — pure-math core.

Uses Dirichlet-Multinomial conjugate priors to model the transition
between LLM-assigned difficulty labels and observed student performance,
then applies Beta-Binomial posteriors per item to decide whether an
item's difficulty label should be changed.

This module has NO database calls. All functions take plain data
and return results.
"""

from __future__ import annotations

import copy

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
