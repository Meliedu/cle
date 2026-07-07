"""Checkpoint status machine — the single source of truth for the publish path.

P3 Decision 1: P1 shipped the full CHECK enum
(``draft→teacher_editing→approved→scheduled→published→live→closed→archived``)
but only ever WROTE ``draft``/``teacher_editing``. P3 adds one authoritative
transition guard here and drives every publish-path endpoint through it, so the
allowed edges live in exactly one place.

Pure functions, no DB. ``IllegalTransition`` mirrors ``SetupGateError``'s typed
``code`` idiom (``services/setup.py``) so the router maps it into the
``APIResponse`` envelope's ``error`` field (``REVIEW_REQUIRED``).
"""
from __future__ import annotations

#: Status values a teacher may still edit cards in (draft lifecycle). Reused by
#: the router's card-CRUD guard. Everything past ``teacher_editing`` is locked.
EDITABLE_STATUSES: frozenset[str] = frozenset({"draft", "teacher_editing"})

#: Allowed status transitions (§4.2). Keys are the current status, values the
#: set of statuses reachable from it. This is the ONLY place edges are declared.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"teacher_editing"}),
    "teacher_editing": frozenset({"approved"}),
    "approved": frozenset(
        {
            "teacher_editing",  # back to editing
            "scheduled",  # schedule a future release
            "published",  # direct publish (immediate release)
        }
    ),
    "scheduled": frozenset({"published"}),
    "published": frozenset({"live"}),
    "live": frozenset({"closed"}),
    "closed": frozenset({"archived"}),
    "archived": frozenset(),  # terminal
}


class IllegalTransition(Exception):
    """Raised when a checkpoint status transition is not permitted.

    ``code`` is the typed error the router maps into the ``APIResponse``
    envelope (``REVIEW_REQUIRED``), mirroring ``SetupGateError.code`` in
    ``services/setup.py``.
    """

    def __init__(self, from_status: str, to_status: str) -> None:
        message = (
            f"Illegal checkpoint transition: '{from_status}' -> '{to_status}'"
        )
        super().__init__(message)
        self.code = "REVIEW_REQUIRED"
        self.message = message
        self.from_status = from_status
        self.to_status = to_status


def assert_transition(from_status: str, to_status: str) -> None:
    """Assert a status transition is allowed, else raise ``IllegalTransition``.

    Returns ``None`` on success. Unknown ``from``/``to`` values are illegal by
    construction (they are not in the allowed-edge map), so callers never need a
    separate validity check.
    """
    if to_status not in _ALLOWED_TRANSITIONS.get(from_status, frozenset()):
        raise IllegalTransition(from_status, to_status)


def is_editable(status: str) -> bool:
    """Whether card CRUD is permitted for a checkpoint in ``status``."""
    return status in EDITABLE_STATUSES
