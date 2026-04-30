"""Scoring formulas for the decision engine.

Coefficients are initial values per spec §Scoring; the quarterly
``tune_action_coefficients`` job retunes them from ``action_outcomes``
telemetry. Until that job has fired, ``DEFAULT_COEFFS`` stands.

All scores are returned as ``float`` for ergonomics. The materialiser
quantizes to ``Decimal(7,3)`` before persisting (matches
``next_actions.priority_score`` column type).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence

DEFAULT_COEFFS: Mapping[str, float] = {
    "prep_meeting": 3.0,
    "complete_assignment": 5.0,
    "practice_weakness": 2.0,
    "flashcard_review": 1.5,
    "catch_up_reading": 1.0,
}


def score_prep_meeting(
    *,
    meeting_concept_weights: Sequence[tuple[float, float]],
    days_until_meeting: float,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """3.0 × P_m × 1/(1 + S_m), where P_m = Σ weight × (1 − mastery)."""
    if not meeting_concept_weights:
        return 0.0
    p_m = sum(w * max(0.0, 1.0 - m) for w, m in meeting_concept_weights)
    return coeffs["prep_meeting"] * p_m * (1.0 / (1.0 + max(0.0, days_until_meeting)))


def score_complete_assignment(
    *,
    assignment_weight: Decimal | None,
    days_until_due: float,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """5.0 × assignment.weight × 1/(1 + D_a). Treats ``None`` weight as 1.0."""
    w = float(assignment_weight) if assignment_weight is not None else 1.0
    return coeffs["complete_assignment"] * w * (1.0 / (1.0 + max(0.0, days_until_due)))


def score_practice_weakness(
    *,
    mastery: float,
    confidence: float,
    recency_factor: float = 1.0,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """2.0 × (1 − mastery) × confidence × recency_factor."""
    return (
        coeffs["practice_weakness"]
        * max(0.0, 1.0 - mastery)
        * max(0.0, min(1.0, confidence))
        * recency_factor
    )


def score_flashcard_review(
    *,
    cards_due_count: int,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """1.5 × cards_due_count."""
    return coeffs["flashcard_review"] * max(0, cards_due_count)


def score_catch_up_reading(
    *,
    days_overdue: int,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """1.0 × (days_overdue + 1)."""
    return coeffs["catch_up_reading"] * (max(0, days_overdue) + 1)
