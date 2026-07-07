"""T1: status-machine transition helper (pure, no DB).

``app/services/checkpoints.py`` is the single source of truth every publish-path
endpoint routes through (P3 Decision 1). It validates the P1 status enum
(``draft→teacher_editing→approved→scheduled→published→live→closed→archived``)
plus the ``approved→teacher_editing`` back-edge and the ``approved→published``
direct-publish shortcut. Every other transition raises ``IllegalTransition``
carrying ``code="REVIEW_REQUIRED"`` (mirroring ``SetupGateError.code``).
"""
import pytest

from app.services.checkpoints import (
    IllegalTransition,
    assert_transition,
    is_editable,
)

# The exact spec edges T1 allows (see plan T1 / Decision 1).
LEGAL_EDGES = [
    ("draft", "teacher_editing"),
    ("teacher_editing", "approved"),
    ("approved", "teacher_editing"),  # back-edge (return to editing)
    ("approved", "scheduled"),
    ("scheduled", "published"),
    ("published", "live"),
    ("live", "closed"),
    ("closed", "archived"),
    ("approved", "published"),  # direct publish (immediate release)
]

# A representative set of illegal edges — skips, reversals, and self-loops.
ILLEGAL_EDGES = [
    ("draft", "approved"),  # skip teacher_editing
    ("draft", "published"),  # skip the whole chain
    ("teacher_editing", "published"),  # skip approved
    ("teacher_editing", "draft"),  # illegal reversal
    ("scheduled", "live"),  # skip published
    ("published", "closed"),  # skip live
    ("published", "scheduled"),  # illegal reversal
    ("live", "archived"),  # skip closed
    ("closed", "published"),  # reopen not allowed
    ("archived", "closed"),  # terminal state
    ("archived", "draft"),  # terminal state
    ("draft", "draft"),  # self-loop
    ("approved", "approved"),  # self-loop
]


@pytest.mark.parametrize("from_status,to_status", LEGAL_EDGES)
def test_legal_transition_passes(from_status: str, to_status: str) -> None:
    # Should not raise.
    assert_transition(from_status, to_status) is None


@pytest.mark.parametrize("from_status,to_status", ILLEGAL_EDGES)
def test_illegal_transition_raises_review_required(
    from_status: str, to_status: str
) -> None:
    with pytest.raises(IllegalTransition) as exc:
        assert_transition(from_status, to_status)
    assert exc.value.code == "REVIEW_REQUIRED"


def test_illegal_transition_carries_states_in_message() -> None:
    with pytest.raises(IllegalTransition) as exc:
        assert_transition("draft", "published")
    assert "draft" in str(exc.value)
    assert "published" in str(exc.value)


def test_unknown_status_raises_review_required() -> None:
    with pytest.raises(IllegalTransition) as exc:
        assert_transition("draft", "bogus")
    assert exc.value.code == "REVIEW_REQUIRED"


@pytest.mark.parametrize(
    "status,editable",
    [
        ("draft", True),
        ("teacher_editing", True),
        ("approved", False),
        ("scheduled", False),
        ("published", False),
        ("live", False),
        ("closed", False),
        ("archived", False),
    ],
)
def test_is_editable(status: str, editable: bool) -> None:
    assert is_editable(status) is editable
