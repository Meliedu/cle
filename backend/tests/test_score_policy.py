"""Unit tests for the score-policy publish gate (P5 B4, Decision 7).

``assert_score_policy_complete`` is a PURE function — no DB, no HTTP resolution,
no commit. It duck-types the required publish-settings off ANY graded/score-bearing
artifact (``Quiz`` or ``Activity``) and raises a typed ``SCORE_POLICY_INCOMPLETE``
422 listing EXACTLY the absent required fields. The function ALWAYS checks; the
caller decides whether to invoke it (practice/participation callers simply don't).
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.score_policy import assert_score_policy_complete


def _artifact(**overrides):
    """A fully-specified graded artifact; override fields to make them absent."""
    base = {
        "score_category_id": "11111111-1111-1111-1111-111111111111",
        "points": 10,
        "grading_mode": "auto",
        "due_at": "2026-08-01T00:00:00Z",
        "close_at": "2026-08-02T00:00:00Z",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_complete_artifact_returns_none():
    assert assert_score_policy_complete(_artifact()) is None


def test_complete_with_only_due_at_is_ok():
    # A deadline counts as present if EITHER due_at OR close_at is set.
    assert assert_score_policy_complete(_artifact(close_at=None)) is None


def test_complete_with_only_close_at_is_ok():
    assert assert_score_policy_complete(_artifact(due_at=None)) is None


def test_missing_score_category_raises():
    with pytest.raises(HTTPException) as exc:
        assert_score_policy_complete(_artifact(score_category_id=None))
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "SCORE_POLICY_INCOMPLETE"
    assert exc.value.detail["missing"] == ["score_category_id"]


def test_missing_points_raises():
    with pytest.raises(HTTPException) as exc:
        assert_score_policy_complete(_artifact(points=None))
    assert exc.value.detail["missing"] == ["points"]


def test_missing_grading_mode_raises():
    with pytest.raises(HTTPException) as exc:
        assert_score_policy_complete(_artifact(grading_mode=None))
    assert exc.value.detail["missing"] == ["grading_mode"]


def test_missing_both_deadlines_reports_single_deadline_entry():
    with pytest.raises(HTTPException) as exc:
        assert_score_policy_complete(_artifact(due_at=None, close_at=None))
    assert exc.value.detail["missing"] == ["deadline"]


def test_all_missing_lists_every_absent_field_in_order():
    with pytest.raises(HTTPException) as exc:
        assert_score_policy_complete(
            SimpleNamespace(
                score_category_id=None,
                points=None,
                grading_mode=None,
                due_at=None,
                close_at=None,
            )
        )
    assert exc.value.detail["missing"] == [
        "score_category_id",
        "points",
        "grading_mode",
        "deadline",
    ]


def test_multiple_missing_subset():
    with pytest.raises(HTTPException) as exc:
        assert_score_policy_complete(_artifact(points=None, grading_mode=None))
    assert exc.value.detail["missing"] == ["points", "grading_mode"]


def test_detail_has_message():
    with pytest.raises(HTTPException) as exc:
        assert_score_policy_complete(_artifact(points=None))
    assert isinstance(exc.value.detail["message"], str)
    assert exc.value.detail["message"]


def test_works_on_missing_attributes_via_getattr():
    # Duck-typed: an object lacking the attributes entirely is treated as absent.
    with pytest.raises(HTTPException) as exc:
        assert_score_policy_complete(SimpleNamespace())
    assert exc.value.detail["missing"] == [
        "score_category_id",
        "points",
        "grading_mode",
        "deadline",
    ]
