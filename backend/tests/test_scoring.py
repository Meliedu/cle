from decimal import Decimal

from app.services.scoring import (
    DEFAULT_COEFFS,
    score_catch_up_reading,
    score_complete_assignment,
    score_flashcard_review,
    score_practice_weakness,
    score_prep_meeting,
)


def test_prep_meeting_increases_with_weak_concepts():
    near = score_prep_meeting(
        meeting_concept_weights=[(1.0, 0.3), (1.0, 0.2)],  # high (1 - mastery)
        days_until_meeting=1.0,
        coeffs=DEFAULT_COEFFS,
    )
    far = score_prep_meeting(
        meeting_concept_weights=[(1.0, 0.3), (1.0, 0.2)],
        days_until_meeting=14.0,
        coeffs=DEFAULT_COEFFS,
    )
    assert near > far


def test_complete_assignment_weights_due_date():
    today = score_complete_assignment(
        assignment_weight=Decimal("1.00"),
        days_until_due=0.0,
        coeffs=DEFAULT_COEFFS,
    )
    next_week = score_complete_assignment(
        assignment_weight=Decimal("1.00"),
        days_until_due=7.0,
        coeffs=DEFAULT_COEFFS,
    )
    assert today > next_week
    assert today == DEFAULT_COEFFS["complete_assignment"]


def test_practice_weakness_zero_when_no_evidence():
    # Confidence factor zeroes out a fresh concept (intended — bandit handles cold start).
    s = score_practice_weakness(mastery=0.0, confidence=0.0)
    assert s == 0.0


def test_practice_weakness_grows_with_evidence_gap():
    s_weak = score_practice_weakness(mastery=0.2, confidence=0.8)
    s_mid = score_practice_weakness(mastery=0.5, confidence=0.8)
    assert s_weak > s_mid > 0


def test_flashcard_review_linear_in_due_count():
    five = score_flashcard_review(cards_due_count=5, coeffs=DEFAULT_COEFFS)
    twenty = score_flashcard_review(cards_due_count=20, coeffs=DEFAULT_COEFFS)
    assert twenty == 4 * five


def test_catch_up_reading_grows_with_overdue_days():
    a = score_catch_up_reading(days_overdue=0, coeffs=DEFAULT_COEFFS)
    b = score_catch_up_reading(days_overdue=7, coeffs=DEFAULT_COEFFS)
    assert b > a


def test_prep_meeting_zero_when_no_concepts():
    """Empty concept-weight list is a real runtime path (meeting with no tags yet)."""
    assert score_prep_meeting(meeting_concept_weights=[], days_until_meeting=1.0) == 0.0


def test_complete_assignment_defaults_weight_when_none():
    """Materializer may pass None when an assignment has no weight set."""
    s = score_complete_assignment(
        assignment_weight=None,
        days_until_due=0.0,
        coeffs=DEFAULT_COEFFS,
    )
    assert s == DEFAULT_COEFFS["complete_assignment"]
