"""FSRS-5 neural spaced repetition scheduler.

Replaces fixed SM-2 constants with a learned 19-parameter model.
Falls back to SM-2 for students with fewer than SWITCHOVER_THRESHOLD reviews.

Reference: https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SWITCHOVER_THRESHOLD = 20
TARGET_RETENTION = 0.9
MIN_INTERVAL = 1      # days
MAX_INTERVAL = 180    # days
LEARNING_RATE = 0.01
GRAD_CLIP_NORM = 1.0

# FSRS-5 default parameters (w0–w18)
DEFAULT_PARAMS: list[float] = [
    0.40255,   # w0:  S_0(Again)
    1.18385,   # w1:  S_0(Hard)
    3.173,     # w2:  S_0(Good)
    15.69105,  # w3:  S_0(Easy)
    7.1949,    # w4:  D_0 base
    0.5345,    # w5:  D_0 grade sensitivity
    1.4604,    # w6:  D update grade sensitivity
    0.0046,    # w7:  D mean reversion rate
    1.54575,   # w8:  S_r exponential base
    0.1192,    # w9:  S_r stability decay
    1.01925,   # w10: S_r retrievability bonus
    1.9395,    # w11: S_f base
    0.11,      # w12: S_f difficulty sensitivity
    0.29605,   # w13: S_f stability sensitivity
    2.2698,    # w14: S_f retrievability sensitivity
    0.2315,    # w15: Hard multiplier
    2.9898,    # w16: Easy multiplier
    0.51655,   # w17: Short-term grade sensitivity
    0.6621,    # w18: Short-term offset
]

# Grade mapping: SM-2 quality (0-5) -> FSRS grade (1-4)
GRADE_MAP: dict[int, int] = {
    0: 1,  # Again -> 1
    2: 2,  # Hard  -> 2
    4: 3,  # Good  -> 3
    5: 4,  # Easy  -> 4
}


# ---------------------------------------------------------------------------
# FSRS Scheduler
# ---------------------------------------------------------------------------


class FSRSScheduler:
    """Stateless FSRS-5 computation engine.

    All methods are pure functions of the parameters passed in.
    No database access — the caller handles persistence.
    """

    def __init__(self, params: list[float] | None = None) -> None:
        self.w = list(params or DEFAULT_PARAMS)

    def compute_retrievability(self, t_days: float, stability: float) -> float:
        """R(t, S) = (1 + t / (9 * S))^(-1)"""
        if stability <= 0:
            return 0.0
        return (1.0 + t_days / (9.0 * stability)) ** (-1)

    def compute_interval(self, stability: float) -> int:
        """Derive interval from stability at target retention.

        I = 9 * S * (1/R_target - 1)
        At R_target=0.9, I = S.
        """
        interval = 9.0 * stability * (1.0 / TARGET_RETENTION - 1.0)
        return max(MIN_INTERVAL, min(MAX_INTERVAL, round(interval)))

    def initial_stability(self, grade: int) -> float:
        """S_0(G) = w[G-1] for grade G in {1,2,3,4}."""
        idx = max(0, min(3, grade - 1))
        return max(0.1, self.w[idx])

    def initial_difficulty(self, grade: int) -> float:
        """D_0(G) = w4 - e^(w5*(G-1)) + 1, clamped to [1, 10]."""
        d = self.w[4] - math.exp(self.w[5] * (grade - 1)) + 1.0
        return max(1.0, min(10.0, d))

    def update_difficulty(self, d: float, grade: int) -> float:
        """D' = w7*D_0(4) + (1-w7)*(D - w6*(G-3)), clamped to [1, 10]."""
        d_new = self.w[7] * self.initial_difficulty(4) + (1.0 - self.w[7]) * (
            d - self.w[6] * (grade - 3)
        )
        return max(1.0, min(10.0, d_new))

    def stability_after_recall(
        self, d: float, s: float, r: float, grade: int
    ) -> float:
        """S'_r for successful recall (grade >= 2)."""
        if grade == 2:
            multiplier = self.w[15]  # Hard
        elif grade == 4:
            multiplier = self.w[16]  # Easy
        else:
            multiplier = 1.0  # Good (grade 3)

        s_new = s * (
            math.exp(self.w[8])
            * (11.0 - d)
            * s ** (-self.w[9])
            * (math.exp(self.w[10] * (1.0 - r)) - 1.0)
            * multiplier
            + 1.0
        )
        return max(0.1, s_new)

    def stability_after_forget(self, d: float, s: float, r: float) -> float:
        """S'_f for lapse (grade == 1, Again)."""
        s_new = (
            self.w[11]
            * d ** (-self.w[12])
            * ((s + 1.0) ** self.w[13] - 1.0)
            * math.exp(self.w[14] * (1.0 - r))
        )
        return max(0.1, min(s, s_new))  # S'_f should not exceed S

    def stability_short_term(self, s: float, grade: int) -> float:
        """S'_s = S * e^(w17 * (G - 3 + w18)) for same-day reviews."""
        s_new = s * math.exp(self.w[17] * (grade - 3 + self.w[18]))
        return max(0.1, s_new)

    def next_state(
        self,
        grade: int,
        stability: float | None,
        difficulty: float | None,
        elapsed_days: float,
    ) -> tuple[float, float, int]:
        """Compute next (stability, difficulty, interval) after a review.

        If stability/difficulty are None, this is the first review of this card.
        Returns (new_stability, new_difficulty, interval_days).
        """
        if stability is None or difficulty is None:
            # First review
            s = self.initial_stability(grade)
            d = self.initial_difficulty(grade)
        elif elapsed_days < 1.0:
            # Same-day review — use short-term stability formula
            d = self.update_difficulty(difficulty, grade)
            s = self.stability_short_term(stability, grade)
        else:
            r = self.compute_retrievability(elapsed_days, stability)
            d = self.update_difficulty(difficulty, grade)
            if grade == 1:
                s = self.stability_after_forget(d, stability, r)
            else:
                s = self.stability_after_recall(d, stability, r, grade)

        interval = self.compute_interval(s)
        return s, d, interval


# ---------------------------------------------------------------------------
# SM-2 fallback (extracted from api/flashcards.py, unchanged algorithm)
# ---------------------------------------------------------------------------


def sm2_update(
    quality: int,
    ease_factor: float,
    interval_days: int,
    repetitions: int,
) -> tuple[float, int, int]:
    """Classic SM-2 algorithm. Returns (new_ef, new_interval, new_reps)."""
    if quality < 3:
        new_reps = 0
        new_interval = 0
    else:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval_days * ease_factor)
        new_reps = repetitions + 1

    new_ef = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(new_ef, 1.3)
    return new_ef, new_interval, new_reps


# ---------------------------------------------------------------------------
# Online parameter learning
# ---------------------------------------------------------------------------


def update_parameters(
    params: list[float],
    predicted_r: float,
    actual_recall: bool,
    stability: float = 1.0,
    difficulty: float = 5.0,
    elapsed_days: float = 1.0,
    grade: int = 3,
) -> list[float]:
    """One-step SGD with per-parameter gradients via numerical differentiation.

    Computes dLoss/dw_i = loss_signal * dS'/dw_i where:
    - loss_signal = (R_predicted - y) captures how wrong the prediction was
    - dS'/dw_i captures each parameter's influence on the stability formula

    Uses finite differences on next_state to get per-parameter sensitivities.
    L2 norm clipping prevents wild updates.

    Returns a new list of 19 floats (updated parameters).
    """
    y = 1.0 if actual_recall else 0.0
    eps = 1e-7

    # Loss signal: positive = over-predicted recall, negative = under-predicted
    r_c = max(eps, min(1.0 - eps, predicted_r))
    loss_signal = r_c - y

    # Base stability from current parameters
    base_sched = FSRSScheduler(params)
    s_base, _, _ = base_sched.next_state(grade, stability, difficulty, elapsed_days)

    # Per-parameter gradient via finite differences on stability
    delta = 1e-4
    grads: list[float] = []
    for i in range(len(params)):
        params_up = list(params)
        params_up[i] += delta
        s_up, _, _ = FSRSScheduler(params_up).next_state(
            grade, stability, difficulty, elapsed_days
        )
        ds_dwi = (s_up - s_base) / delta
        grads.append(loss_signal * ds_dwi)

    # L2 norm clipping
    grad_norm = math.sqrt(sum(g * g for g in grads))
    if grad_norm > GRAD_CLIP_NORM:
        scale = GRAD_CLIP_NORM / grad_norm
        grads = [g * scale for g in grads]

    new_params = [
        params[i] - LEARNING_RATE * grads[i]
        for i in range(len(params))
    ]
    return new_params


# ---------------------------------------------------------------------------
# SM-2 to FSRS state initialization
# ---------------------------------------------------------------------------


def initialize_from_sm2(
    ease_factor: float, interval_days: int
) -> tuple[float, float]:
    """Convert SM-2 state to FSRS state at switchover.

    Returns (stability, difficulty).
    """
    stability = max(0.1, float(interval_days))
    difficulty = max(1.0, min(10.0, 11.0 - ease_factor * 4.0))
    return stability, difficulty
