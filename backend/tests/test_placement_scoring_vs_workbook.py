"""Exhaustive equivalence proof: our scoring vs the published workbook formulas.

``placement_scoring.py`` is a transcription of
``Meli_Placement_Test_v1.2_Scoring_and_Calibration.xlsx``. A transcription can
be reviewed by eye, but eyes miss boundary conditions, and a boundary mistake
here silently places a student in the wrong course.

So this file transcribes the Excel formulas a *second* time, independently and
as literally as possible -- straight from the cell text, with no refactoring --
and then checks the two agree on **every one of the 46,656 possible band-score
vectors** (0..5 correct at each of six bands). Exhaustive, not sampled.

The workbook formulas, copied verbatim from the v1.2 file:

    B19  =IF(AND(B16>=3,SUM(B11:B16)/30>=0.7),6,
          IF(AND(B15>=3,SUM(B11:B15)/25>=0.7),5,
          IF(AND(B14>=3,SUM(B11:B14)/20>=0.7),4,
          IF(AND(B13>=3,SUM(B11:B13)/15>=0.7),3,
          IF(AND(B12>=3,SUM(B11:B12)/10>=0.7),2,
          IF(AND(B11>=3,B11/5>=0.7),1,0))))))

    B20  =IF(B19<=1,"LANG1511",IF(B19=2,"LANG1512",IF(B19=3,"LANG1513",
          IF(B19=4,"LANG1514","LANG1515"))))

    B21  =IF(B19<=1,FALSE,IF(B19=2,B11<=2,IF(B19=3,MIN(B11:B12)<=2,
          IF(B19=4,MIN(B11:B13)<=2,IF(B19=5,MIN(B11:B14)<=2,MIN(B11:B15)<=2)))))

    B22  =IF(B19=0,FALSE,IF(B19=6,TRUE,IF(B19=1,B12<=2,IF(B19=2,B13<=2,
          IF(B19=3,B14<=2,IF(B19=4,B15<=2,B16<=2))))))

    B23  =IF(OR(B19=0,D6<27,'Entry'!F4<12,'Entry'!F4>45,B21=TRUE),"Review",
          IF(AND(D6=30,B22=TRUE,IF(B19=1,B11,IF(B19=2,B12,IF(B19=3,B13,
          IF(B19=4,B14,IF(B19=5,B15,B16)))))>=4),"High","Medium"))

    D11:D16  =IF(B11>=4,"Strong",IF(B11=3,"Developing","Not demonstrated"))

where B11..B16 are the per-band correct counts, D6 is the answered count, and
Entry!F4 is the duration in minutes.
"""
from __future__ import annotations

import itertools

import pytest

from app.services.placement_scoring import (
    BANDS,
    COURSE_BY_BAND,
    ScoringPolicy,
    band_evidence_labels,
    has_clear_next_band_boundary,
    has_lower_band_break,
    highest_sustained_band,
)

# ---------------------------------------------------------------------------
# Literal transcriptions. Deliberately unfactored: they should read like the
# spreadsheet, not like good Python, so a reviewer can diff them against the
# cell text above line by line.
# ---------------------------------------------------------------------------


def xl_b19(b: dict[int, int]) -> int:
    """Highest sustained band."""
    if b[6] >= 3 and sum(b[i] for i in range(1, 7)) / 30 >= 0.7:
        return 6
    if b[5] >= 3 and sum(b[i] for i in range(1, 6)) / 25 >= 0.7:
        return 5
    if b[4] >= 3 and sum(b[i] for i in range(1, 5)) / 20 >= 0.7:
        return 4
    if b[3] >= 3 and sum(b[i] for i in range(1, 4)) / 15 >= 0.7:
        return 3
    if b[2] >= 3 and sum(b[i] for i in range(1, 3)) / 10 >= 0.7:
        return 2
    if b[1] >= 3 and b[1] / 5 >= 0.7:
        return 1
    return 0


def xl_b20(b19: int) -> str:
    """Provisional course."""
    if b19 <= 1:
        return "LANG1511"
    if b19 == 2:
        return "LANG1512"
    if b19 == 3:
        return "LANG1513"
    if b19 == 4:
        return "LANG1514"
    return "LANG1515"


def xl_b21(b: dict[int, int], b19: int) -> bool:
    """Lower-band break."""
    if b19 <= 1:
        return False
    if b19 == 2:
        return b[1] <= 2
    if b19 == 3:
        return min(b[1], b[2]) <= 2
    if b19 == 4:
        return min(b[1], b[2], b[3]) <= 2
    if b19 == 5:
        return min(b[1], b[2], b[3], b[4]) <= 2
    return min(b[1], b[2], b[3], b[4], b[5]) <= 2


def xl_b22(b: dict[int, int], b19: int) -> bool:
    """Clear next-band boundary."""
    if b19 == 0:
        return False
    if b19 == 6:
        return True
    if b19 == 1:
        return b[2] <= 2
    if b19 == 2:
        return b[3] <= 2
    if b19 == 3:
        return b[4] <= 2
    if b19 == 4:
        return b[5] <= 2
    return b[6] <= 2


def xl_b23(
    b: dict[int, int], b19: int, b21: bool, b22: bool, answered: int, minutes: float
) -> str:
    """Confidence."""
    if b19 == 0 or answered < 27 or minutes < 12 or minutes > 45 or b21 is True:
        return "Review"
    at_band = (
        b[1] if b19 == 1
        else b[2] if b19 == 2
        else b[3] if b19 == 3
        else b[4] if b19 == 4
        else b[5] if b19 == 5
        else b[6]
    )
    if answered == 30 and b22 is True and at_band >= 4:
        return "High"
    return "Medium"


def xl_d11(value: int) -> str:
    """Evidence status."""
    if value >= 4:
        return "Strong"
    if value == 3:
        return "Developing"
    return "Not demonstrated"


#: Every possible band-score vector: 6 bands x 0..5 correct = 46,656.
ALL_VECTORS = [
    dict(zip(BANDS, combo)) for combo in itertools.product(range(6), repeat=6)
]

_LABEL = {"strong": "Strong", "developing": "Developing", "not_demonstrated": "Not demonstrated"}
_CONFIDENCE = {"high": "High", "medium": "Medium", "review": "Review"}


def test_the_search_space_is_actually_exhaustive():
    assert len(ALL_VECTORS) == 6**6 == 46_656


def test_highest_sustained_band_matches_the_workbook_on_every_vector():
    policy = ScoringPolicy()
    mismatches = [
        (b, highest_sustained_band(b, policy), xl_b19(b))
        for b in ALL_VECTORS
        if highest_sustained_band(b, policy) != xl_b19(b)
    ]
    assert not mismatches, f"{len(mismatches)} mismatches, first: {mismatches[0]}"


def test_provisional_course_matches_the_workbook_on_every_vector():
    policy = ScoringPolicy()
    for b in ALL_VECTORS:
        band = highest_sustained_band(b, policy)
        assert COURSE_BY_BAND[band] == xl_b20(band), b


def test_lower_band_break_matches_the_workbook_on_every_vector():
    policy = ScoringPolicy()
    mismatches = [
        b
        for b in ALL_VECTORS
        if has_lower_band_break(b, highest_sustained_band(b, policy))
        != xl_b21(b, xl_b19(b))
    ]
    assert not mismatches, f"{len(mismatches)} mismatches, first: {mismatches[0]}"


def test_clear_boundary_matches_the_workbook_on_every_vector():
    policy = ScoringPolicy()
    mismatches = [
        b
        for b in ALL_VECTORS
        if has_clear_next_band_boundary(b, highest_sustained_band(b, policy))
        != xl_b22(b, xl_b19(b))
    ]
    assert not mismatches, f"{len(mismatches)} mismatches, first: {mismatches[0]}"


def test_evidence_labels_match_the_workbook_on_every_vector():
    for b in ALL_VECTORS:
        ours = band_evidence_labels(b)
        for band in BANDS:
            assert _LABEL[ours[band]] == xl_d11(b[band]), (b, band)


@pytest.mark.parametrize(
    "answered,minutes",
    [
        (30, 30.0),   # the ordinary case
        (30, 12.0),   # exactly the fast threshold: NOT flagged
        (30, 11.9),   # just under: flagged
        (30, 45.0),   # exactly the long threshold: NOT flagged
        (30, 45.1),   # just over: flagged
        (27, 30.0),   # exactly the completeness threshold: NOT flagged
        (26, 30.0),   # just under: flagged
        (0, 30.0),    # nothing answered
    ],
)
def test_confidence_matches_the_workbook_on_every_vector(answered, minutes):
    """The boundary conditions are the whole point of doing this exhaustively.

    ``<27``, ``<12`` and ``>45`` are strict in the workbook, so 27, 12 and 45
    themselves are all inside the acceptable band. An off-by-one here would move
    real students between "high confidence" and "needs review".
    """
    from app.services.placement_scoring import _confidence

    policy = ScoringPolicy()
    for b in ALL_VECTORS:
        band = highest_sustained_band(b, policy)
        break_below = has_lower_band_break(b, band)
        boundary = has_clear_next_band_boundary(b, band)

        ours = _confidence(
            scores=b,
            answered=answered,
            sustained=band,
            lower_break=break_below,
            clear_boundary=boundary,
            duration_seconds=int(minutes * 60),
            policy=policy,
            # No system-level triggers: this compares against the workbook,
            # which has no telemetry and cannot express them.
            flags=[],
        )
        expected = xl_b23(b, band, break_below, boundary, answered, minutes)
        assert _CONFIDENCE[ours] == expected, (b, answered, minutes)


def test_band_one_is_the_only_band_needing_four_of_five():
    """A property of the two rules interacting, asserted against the workbook.

    Band 1's cumulative denominator is its own five items, so 3/5 = 0.6 fails
    the 0.7 threshold that every other band can clear with help from below.
    """
    policy = ScoringPolicy()
    for score in range(6):
        vector = {1: score, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
        ours = highest_sustained_band(vector, policy)
        assert ours == xl_b19(vector)
        assert ours == (1 if score >= 4 else 0)
