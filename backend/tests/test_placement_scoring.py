"""Scoring truth tests for the placement provisional recommendation.

The strongest available oracle is the published scoring workbook: CLE verified
seven scenarios against it and shipped the output in
``_qa/xlsx/scoring-scenario-verification.ndjson``. Two of those are reproduced
here against the **real extracted item bank**, not fixtures, so a transcription
error in either the rules or the bank fails the suite.

The remainder are boundary cases the workbook's seven scenarios do not reach.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.placement_scoring import (
    BANDS,
    COURSE_BY_BAND,
    REVIEW_FORCING_FLAGS,
    ScoredResponse,
    ScoringPolicy,
    band_evidence_labels,
    band_scores,
    has_clear_next_band_boundary,
    has_lower_band_break,
    highest_sustained_band,
    is_correct,
    normalise_response,
    score_attempt,
)

BANK_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "data" / "placement" / "meli-placement-v1.2.json"
)


@pytest.fixture(scope="module")
def bank() -> dict:
    if not BANK_PATH.exists():  # pragma: no cover - guarded by test_placement_bank
        pytest.skip(f"item bank not generated at {BANK_PATH}")
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _responses(
    bank: dict,
    form_code: str,
    *,
    answer: str = "correct",
    bands_correct: set[int] | None = None,
    time_spent_ms: int | None = None,
) -> list[ScoredResponse]:
    """Build a full 30-response attempt from the real bank.

    ``bands_correct`` restricts correctness to those bands; every other item
    gets a deliberately wrong response, which is how the workbook's Bands 1-3
    scenario was constructed (it wrote "Z" into the non-target rows).
    """
    form = next(f for f in bank["forms"] if f["form_code"] == form_code)
    out: list[ScoredResponse] = []
    for item in form["items"]:
        key = item["restricted"]["correct_answer"]
        band = item["restricted"]["legacy_band"]
        if answer == "blank":
            response = None
        elif bands_correct is not None and band not in bands_correct:
            response = "Z"
        elif answer == "correct":
            response = key
        else:
            response = answer
        out.append(
            ScoredResponse(
                question_number=item["question_number"],
                legacy_band=band,
                section=item["section"],
                response=response,
                correct_answer=key,
                key_disputed=False,
                time_spent_ms=time_spent_ms,
            )
        )
    return out


# --------------------------------------------------------------------------
# Response normalisation (Entry!G9)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("b", "B"),
        (" B ", "B"),
        ("C-A-B", "CAB"),
        ("c a b", "CAB"),
        ("C - A - B", "CAB"),
        (None, ""),
        ("", ""),
    ],
)
def test_normalise_response_matches_workbook_substitution(raw, expected):
    assert normalise_response(raw) == expected


def test_sequence_answer_accepts_every_written_form():
    for written in ("C-A-B", "cab", "C A B", "c-a-b"):
        assert is_correct(written, "C-A-B")


def test_sequence_answer_rejects_a_different_order():
    assert not is_correct("A-B-C", "C-A-B")


def test_blank_is_never_correct_even_against_a_blank_key():
    assert not is_correct(None, "")
    assert not is_correct("", "B")


# --------------------------------------------------------------------------
# CLE-verified workbook scenarios, replayed on the real bank
# --------------------------------------------------------------------------


@pytest.mark.parametrize("form_code", ["A", "B", "C", "D", "E"])
def test_perfect_form_matches_verified_workbook_output(bank, form_code):
    """`_qa/xlsx/scoring-scenario-verification.ndjson`, scenarios "A-E perfect".

    Verified output: 30/30, five correct at every band, highest sustained band
    6, provisional LANG1515, no lower-band break, clear boundary, High
    confidence, and no review flags.
    """
    result = score_attempt(
        _responses(bank, form_code), duration_seconds=30 * 60
    )

    assert result.raw_score == 30
    assert result.answered_count == 30
    assert result.band_scores == {band: 5 for band in BANDS}
    assert result.skill_scores == {
        "listening": {"correct": 12, "total": 12},
        "language_use": {"correct": 6, "total": 6},
        "reading": {"correct": 12, "total": 12},
    }
    assert result.highest_sustained_band == 6
    assert result.provisional_course == "LANG1515"
    assert result.lower_band_break is False
    assert result.clear_next_band_boundary is True
    assert result.confidence == "high"
    # The advisory ceiling flag is expected and must not force review.
    assert not [f for f in result.review_flags if f in REVIEW_FORCING_FLAGS]


def test_bands_one_to_three_only_matches_verified_workbook_output(bank):
    """Scenario "A bands 1-3 only": sustained band 3, provisional LANG1513."""
    result = score_attempt(
        _responses(bank, "A", bands_correct={1, 2, 3}), duration_seconds=30 * 60
    )

    assert result.band_scores == {1: 5, 2: 5, 3: 5, 4: 0, 5: 0, 6: 0}
    assert result.highest_sustained_band == 3
    assert result.provisional_course == "LANG1513"
    assert result.lower_band_break is False
    assert result.clear_next_band_boundary is True
    assert result.confidence == "high"
    assert result.review_flags == []


# --------------------------------------------------------------------------
# Sustained-band rule (Summary!B19)
# --------------------------------------------------------------------------


def test_band_one_needs_four_of_five_not_three():
    """The workbook's "Requires 4/5 at Band 1" note, as an executable claim.

    3/5 clears the band minimum but 0.6 < 0.7 fails the cumulative rule, so the
    two rules together make band 1 stricter than every other band.
    """
    policy = ScoringPolicy()
    assert highest_sustained_band({1: 3, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}, policy) == 0
    assert highest_sustained_band({1: 4, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}, policy) == 1


def test_band_minimum_alone_is_not_enough_without_cumulative_accuracy():
    # 3/5 at band 3 satisfies the minimum, but 3+0+3 = 6 of 15 is 0.40.
    policy = ScoringPolicy()
    assert highest_sustained_band({1: 3, 2: 0, 3: 3, 4: 0, 5: 0, 6: 0}, policy) == 0


def test_cumulative_accuracy_alone_is_not_enough_without_the_band_minimum():
    # 5+5+2 = 12 of 15 is 0.80, but band 3 itself is only 2/5.
    policy = ScoringPolicy()
    assert highest_sustained_band({1: 5, 2: 5, 3: 2, 4: 0, 5: 0, 6: 0}, policy) == 2


def test_sustained_band_takes_the_highest_qualifying_band_not_the_first():
    policy = ScoringPolicy()
    scores = {1: 5, 2: 5, 3: 5, 4: 5, 5: 3, 6: 3}
    # Band 6: 3/5 at band, 26/30 = 0.867 through -> qualifies, and it is highest.
    assert highest_sustained_band(scores, policy) == 6


def test_zero_evidence_maps_to_band_zero_and_the_entry_course():
    policy = ScoringPolicy()
    assert highest_sustained_band({band: 0 for band in BANDS}, policy) == 0
    assert COURSE_BY_BAND[0] == "LANG1511"


@pytest.mark.parametrize(
    "band,course",
    [(0, "LANG1511"), (1, "LANG1511"), (2, "LANG1512"), (3, "LANG1513"),
     (4, "LANG1514"), (5, "LANG1515"), (6, "LANG1515")],
)
def test_provisional_course_map_matches_rules_sheet(band, course):
    assert COURSE_BY_BAND[band] == course


# --------------------------------------------------------------------------
# Profile shape (Summary!B21, B22, D11:D16)
# --------------------------------------------------------------------------


def test_lower_band_break_detects_a_weak_band_below_the_sustained_one():
    assert has_lower_band_break({1: 5, 2: 2, 3: 5, 4: 5, 5: 0, 6: 0}, 4) is True


def test_lower_band_break_ignores_bands_at_or_above_the_sustained_one():
    # Bands 5 and 6 are weak, but they are above the sustained band 4.
    assert has_lower_band_break({1: 5, 2: 5, 3: 5, 4: 4, 5: 0, 6: 0}, 4) is False


def test_lower_band_break_is_false_at_band_one_and_below():
    assert has_lower_band_break({1: 2, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}, 1) is False
    assert has_lower_band_break({1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}, 0) is False


def test_clear_boundary_requires_the_next_band_to_be_weak():
    assert has_clear_next_band_boundary({3: 5, 4: 2}, 3) is True
    assert has_clear_next_band_boundary({3: 5, 4: 3}, 3) is False


def test_band_six_boundary_is_true_because_there_is_no_band_seven():
    assert has_clear_next_band_boundary({6: 5}, 6) is True


def test_band_zero_has_no_boundary():
    assert has_clear_next_band_boundary({1: 0}, 0) is False


def test_band_evidence_labels_are_words_not_scores():
    labels = band_evidence_labels({1: 5, 2: 4, 3: 3, 4: 2, 5: 0, 6: 0})
    assert labels == {
        1: "strong", 2: "strong", 3: "developing",
        4: "not_demonstrated", 5: "not_demonstrated", 6: "not_demonstrated",
    }


# --------------------------------------------------------------------------
# The eight mandatory review triggers
# --------------------------------------------------------------------------


def test_fewer_than_twenty_seven_answers_forces_review(bank):
    responses = _responses(bank, "A")
    blanked = [
        ScoredResponse(**{**r.__dict__, "response": None}) if r.question_number > 26 else r
        for r in responses
    ]
    result = score_attempt(blanked, duration_seconds=30 * 60)
    assert result.answered_count == 26
    assert "incomplete_answers" in result.review_flags
    assert result.confidence == "review"


def test_exactly_twenty_seven_answers_does_not_trigger_incomplete(bank):
    responses = _responses(bank, "A")
    blanked = [
        ScoredResponse(**{**r.__dict__, "response": None}) if r.question_number > 27 else r
        for r in responses
    ]
    result = score_attempt(blanked, duration_seconds=30 * 60)
    assert result.answered_count == 27
    assert "incomplete_answers" not in result.review_flags


def test_duration_under_twelve_minutes_forces_review(bank):
    result = score_attempt(_responses(bank, "A"), duration_seconds=11 * 60)
    assert "duration_too_short" in result.review_flags
    assert result.confidence == "review"


def test_duration_of_exactly_twelve_minutes_is_not_flagged(bank):
    """The workbook tests ``F4<12``, so twelve itself is inside the band."""
    result = score_attempt(_responses(bank, "A"), duration_seconds=12 * 60)
    assert "duration_too_short" not in result.review_flags


def test_duration_over_forty_five_minutes_forces_review(bank):
    result = score_attempt(_responses(bank, "A"), duration_seconds=46 * 60)
    assert "duration_too_long" in result.review_flags
    assert result.confidence == "review"


def test_approved_extended_time_explains_a_long_sitting(bank):
    result = score_attempt(
        _responses(bank, "A"),
        duration_seconds=60 * 60,
        accommodation={"extended_time": True},
    )
    assert "duration_too_long" not in result.review_flags


def test_extended_time_never_explains_an_impossibly_fast_sitting(bank):
    """An accommodation grants more time; it cannot make five minutes plausible."""
    result = score_attempt(
        _responses(bank, "A"),
        duration_seconds=5 * 60,
        accommodation={"extended_time": True},
    )
    assert "duration_too_short" in result.review_flags


def test_non_monotonic_profile_forces_review(bank):
    responses = _responses(bank, "A", bands_correct={1, 3, 4, 5, 6})
    # Band 2 is now 0/5 while higher bands are strong.
    result = score_attempt(responses, duration_seconds=30 * 60)
    assert result.band_scores[2] == 0
    assert "lower_band_break" in result.review_flags
    assert result.confidence == "review"


def test_declared_background_more_than_one_band_away_forces_review(bank):
    result = score_attempt(
        _responses(bank, "A", bands_correct={1, 2, 3}),
        duration_seconds=30 * 60,
        declared_band=6,
    )
    assert "declared_background_mismatch" in result.review_flags
    assert result.confidence == "review"


def test_declared_background_one_band_away_is_within_tolerance(bank):
    result = score_attempt(
        _responses(bank, "A", bands_correct={1, 2, 3}),
        duration_seconds=30 * 60,
        declared_band=4,
    )
    assert "declared_background_mismatch" not in result.review_flags


def test_technical_interruption_forces_review(bank):
    result = score_attempt(
        _responses(bank, "A"),
        duration_seconds=30 * 60,
        interruptions=[{"kind": "disconnect", "at": "2026-08-01T10:00:00Z"}],
    )
    assert "technical_interruption" in result.review_flags
    assert result.confidence == "review"


def test_compromised_form_forces_review(bank):
    result = score_attempt(
        _responses(bank, "A"), duration_seconds=30 * 60, form_compromised=True
    )
    assert "form_compromised" in result.review_flags
    assert result.confidence == "review"


def test_attempt_spread_greater_than_one_band_forces_review(bank):
    result = score_attempt(
        _responses(bank, "A", bands_correct={1, 2, 3}),
        duration_seconds=30 * 60,
        prior_attempt_bands=[6],
    )
    assert "attempt_spread" in result.review_flags
    assert result.confidence == "review"


def test_attempt_spread_of_one_band_is_tolerated(bank):
    result = score_attempt(
        _responses(bank, "A", bands_correct={1, 2, 3}),
        duration_seconds=30 * 60,
        prior_attempt_bands=[4],
    )
    assert "attempt_spread" not in result.review_flags


def test_straight_lined_answers_are_flagged(bank):
    result = score_attempt(
        _responses(bank, "A", answer="A"), duration_seconds=30 * 60
    )
    assert "response_pattern_anomaly" in result.review_flags
    assert result.confidence == "review"


def test_impossibly_fast_answering_is_flagged(bank):
    result = score_attempt(
        _responses(bank, "A", time_spent_ms=400), duration_seconds=13 * 60
    )
    assert "response_pattern_anomaly" in result.review_flags


def test_normal_pacing_is_not_flagged_as_a_pattern(bank):
    result = score_attempt(
        _responses(bank, "A", time_spent_ms=30_000), duration_seconds=30 * 60
    )
    assert "response_pattern_anomaly" not in result.review_flags


def test_high_band_result_raises_the_ceiling_flag_as_advisory_only(bank):
    """Spec trigger 8 is recorded, but must not contradict a verified scenario.

    A perfect paper is High confidence in the workbook CLE signed off. The
    ceiling flag still surfaces so a reviewer knows the test cannot discriminate
    above band 5.
    """
    result = score_attempt(_responses(bank, "A"), duration_seconds=30 * 60)
    assert "high_band_ceiling" in result.review_flags
    assert result.confidence == "high"


# --------------------------------------------------------------------------
# Disputed keys
# --------------------------------------------------------------------------


def test_a_disputed_item_is_excluded_from_the_score_and_forces_review(bank):
    responses = _responses(bank, "A")
    disputed = [
        ScoredResponse(**{**r.__dict__, "key_disputed": True}) if r.question_number == 17 else r
        for r in responses
    ]
    result = score_attempt(disputed, duration_seconds=30 * 60)

    # 29 scorable, so the perfect paper now reads 29 -- the missing point is the
    # item nobody can defend, not a mistake the learner made.
    assert result.raw_score == 29
    assert result.scorable_count == 29
    # They still answered 30 questions; effort is not reduced by our defect.
    assert result.answered_count == 30
    assert "item_key_disputed" in result.review_flags
    assert result.confidence == "review"


def test_disputed_item_does_not_shrink_the_skill_denominator(bank):
    responses = _responses(bank, "A")
    disputed = [
        ScoredResponse(**{**r.__dict__, "key_disputed": True}) if r.question_number == 1 else r
        for r in responses
    ]
    result = score_attempt(disputed, duration_seconds=30 * 60)
    assert result.skill_scores["listening"] == {"correct": 11, "total": 12}


# --------------------------------------------------------------------------
# Policy versioning
# --------------------------------------------------------------------------


def test_policy_reads_stored_thresholds():
    policy = ScoringPolicy.from_config(
        {"band_minimum": 4, "cumulative_threshold": 0.8, "version": "v2"}
    )
    assert policy.band_minimum == 4
    assert policy.cumulative_threshold == 0.8
    assert policy.version == "v2"


def test_policy_ignores_unknown_keys_rather_than_refusing_to_score():
    policy = ScoringPolicy.from_config({"band_minimum": 4, "future_knob": 1})
    assert policy.band_minimum == 4


def test_policy_defaults_match_the_published_rules_sheet():
    policy = ScoringPolicy()
    assert policy.band_minimum == 3
    assert policy.cumulative_threshold == 0.7
    assert policy.incomplete_answers_below == 27
    assert policy.fast_duration_minutes == 12
    assert policy.long_duration_minutes == 45
    assert policy.attempt_spread_bands == 1


def test_a_stricter_policy_changes_the_sustained_band(bank):
    strict = ScoringPolicy(band_minimum=5)
    scores = band_scores(_responses(bank, "A", bands_correct={1, 2, 3, 4}))
    assert highest_sustained_band(scores, ScoringPolicy()) == 4
    assert highest_sustained_band(scores, strict) == 4  # 5/5 at band 4 still passes
    assert highest_sustained_band({1: 5, 2: 5, 3: 4, 4: 0, 5: 0, 6: 0}, strict) == 2
