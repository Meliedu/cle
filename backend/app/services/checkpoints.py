"""Checkpoint status machine — the single source of truth for the publish path.

P3 Decision 1: P1 shipped the full CHECK enum
(``draft→teacher_editing→approved→scheduled→published→live→closed→archived``)
but only ever WROTE ``draft``/``teacher_editing``. P3 adds one authoritative
transition guard here and drives every publish-path endpoint through it, so the
allowed edges live in exactly one place.

Pure functions, no DB. ``IllegalTransition`` mirrors ``SetupGateError``'s typed
``code`` idiom (``services/setup.py``) so the router maps it into the
``APIResponse`` envelope's ``error`` field (``REVIEW_REQUIRED``).

P3 T13 adds ``close_due_checkpoints`` — the one DB-touching function in this
module. It is the shared close code path: it walks every eligible checkpoint to
``closed`` through ``assert_transition`` (same guard the T5 manual-close endpoint
uses), so the cron and the teacher button can never diverge on the legal edges.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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


def walk_to_closed(from_status: str) -> tuple[str, ...]:
    """Return the asserted transition path from ``from_status`` to ``closed``.

    ``published→closed`` is a skip-edge (illegal in T1), so a checkpoint that
    never went ``live`` is walked ``published→live→closed`` — each step asserted.
    Any illegal source raises ``IllegalTransition``. This is the single walk both
    the T5 manual-close endpoint and the T13 cron drive their status change
    through, so the legal edges live in exactly one place.
    """
    path: list[str] = []
    status = from_status
    if status == "published":
        assert_transition(status, "live")
        path.append("live")
        status = "live"
    assert_transition(status, "closed")
    path.append("closed")
    return tuple(path)


# --------------------------------------------------------------------------- #
#  P3 T13: close_due_checkpoints cron                                          #
# --------------------------------------------------------------------------- #

#: Source states the cron may auto-close (§4.2). ``scheduled``/``approved`` are
#: pre-release and ``manual`` close_rules never auto-close — see ``_is_close_due``.
_AUTO_CLOSEABLE_STATUSES: tuple[str, ...] = ("published", "live")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    """Treat a naive timestamp as UTC (asyncpg returns tz-aware, but tests that
    build models in-process may hand back naive values)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_close_due(cp, meeting, now: datetime) -> bool:
    """Whether ``cp`` (already known to be in an auto-closeable status) is due.

    - ``at_close_at``    → due once ``close_at <= now``.
    - ``end_of_session`` → due once the linked meeting has ended
      (``scheduled_at + duration_minutes <= now``); falls back to ``close_at``
      when the checkpoint carries no meeting.
    - ``manual`` / NULL / unknown → never auto-closes.
    """
    close_at = _as_aware(cp.close_at)

    if cp.close_rule == "at_close_at":
        return close_at is not None and close_at <= now

    if cp.close_rule == "end_of_session":
        if meeting is not None:
            ends_at = _as_aware(meeting.scheduled_at) + timedelta(
                minutes=meeting.duration_minutes
            )
            return ends_at <= now
        # No session attached — fall back to an explicit close_at if present.
        return close_at is not None and close_at <= now

    return False


async def close_due_checkpoints(session: AsyncSession) -> int:
    """Transition every due ``published``/``live`` checkpoint to ``closed``.

    For each closed checkpoint: route the status change through
    ``assert_transition`` (via ``walk_to_closed``), flip any ``active``
    ``checkpoint_launches`` row to ``closed``, and — best-effort, after commit —
    broadcast a terminal ``closed`` event on the T12 monitor hub. Returns the
    number of checkpoints closed. Idempotent: a second run finds nothing due
    (closed rows drop out of the source-status filter) and returns ``0``.
    """
    # Local imports avoid an import cycle: models pull the ORM registry and the
    # monitor hub imports live_quiz, none of which this pure-guard module needs
    # at import time.
    from app.models.attendance import CheckpointLaunch
    from app.models.checkpoint import Checkpoint
    from app.models.curriculum import CourseMeeting
    from app.services.checkpoint_monitor import broadcast_closed

    now = _utcnow()

    candidates = (
        await session.execute(
            select(Checkpoint).where(
                Checkpoint.status.in_(_AUTO_CLOSEABLE_STATUSES),
                Checkpoint.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    if not candidates:
        return 0

    # Batch-load meetings for the end_of_session candidates in one query.
    meeting_ids = {
        cp.meeting_id for cp in candidates if cp.meeting_id is not None
    }
    meetings: dict[uuid.UUID, CourseMeeting] = {}
    if meeting_ids:
        rows = (
            await session.execute(
                select(CourseMeeting).where(CourseMeeting.id.in_(meeting_ids))
            )
        ).scalars().all()
        meetings = {m.id: m for m in rows}

    closed_ids: list[uuid.UUID] = []
    for cp in candidates:
        meeting = meetings.get(cp.meeting_id) if cp.meeting_id else None
        if not _is_close_due(cp, meeting, now):
            continue
        # Route through the T1 guard — raises IllegalTransition on any bad edge
        # (would abort the whole sweep, which is correct: the map is wrong).
        for target in walk_to_closed(cp.status):
            cp.status = target
        closed_ids.append(cp.id)

    if not closed_ids:
        return 0

    # Close any live QR launch on the now-closed checkpoints.
    await session.execute(
        update(CheckpointLaunch)
        .where(
            CheckpointLaunch.checkpoint_id.in_(closed_ids),
            CheckpointLaunch.status == "active",
        )
        .values(status="closed")
    )

    await session.commit()

    # Best-effort terminal broadcast — a hub failure must never undo the close.
    for cid in closed_ids:
        try:
            await broadcast_closed(session, cid)
        except Exception:  # noqa: BLE001 — non-fatal: the close already committed
            logger.exception(
                "monitor closed-broadcast failed for checkpoint_id=%s", cid
            )

    return len(closed_ids)
