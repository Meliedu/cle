"""Live monitor hub for activities (P5 B10, Decision 6).

REUSE — NOT rebuild. The teacher live-monitor WebSocket rides the SAME
``ConnectionManager`` class that powers the live-quiz hub (``live_quiz.py``) and
the checkpoint monitor (``checkpoint_monitor.py``); we only instantiate a second
module-level ``monitor_manager`` so activity monitor connections live in their
own namespace, keyed by ``str(activity_id)``.

Message shapes (all JSON, ``send_text`` under the hood):
- On connect, the handler sends ``{type: "state", submission_count,
  distribution}`` to the newly-connected socket only.
- ``broadcast_submission`` pushes ``{type: "submission", ...}`` to every
  connected monitor after a student's response commits (the B9 seam).
- ``broadcast_closed`` pushes ``{type: "closed", ...}`` when the activity closes.

``distribution`` is a FORMAT-APPROPRIATE aggregate (mirrors the checkpoint
``confidence_distribution`` idea but per activity ``format``):
- ``swipe`` → ``{"left": n, "right": m}`` (direction tallies across responses).
- ``vote`` → ``{option: count, ...}`` (per-option tallies, zero-filled from the
  activity's ``config.options`` for a stable axis).
- ``comment_reaction`` → ``{reaction: count, ...}`` (histogram over the STACKED
  ``payload.entries``, zero-filled from ``config.reactions``).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.models.activity import Activity, ActivityResponse
from app.services.live_quiz import ConnectionManager

logger = logging.getLogger(__name__)

#: The two swipe directions; always zero-filled so the monitor renders a stable
#: L/R axis even before any student swipes.
SWIPE_DIRECTIONS: tuple[str, ...] = ("left", "right")

#: Second instance of the live-quiz hub class — no new WS framework (Decision 6).
monitor_manager = ConnectionManager()


def _config_keys(config: dict | None, list_key: str) -> list[str]:
    """Extract the stable option/reaction keys from an activity ``config`` list.

    A config entry may be a bare string (``"A"``) or an object carrying an
    identifier (``{"id": "A", ...}``); we pull the string key so the distribution
    can be zero-filled to a stable axis. Unrecognised shapes are skipped.
    """
    keys: list[str] = []
    for item in (config or {}).get(list_key, []) or []:
        if isinstance(item, str):
            keys.append(item)
        elif isinstance(item, dict):
            for field in ("id", "key", "value", "label"):
                candidate = item.get(field)
                if isinstance(candidate, str):
                    keys.append(candidate)
                    break
    return keys


def _swipe_distribution(responses: list[ActivityResponse]) -> dict[str, int]:
    dist = {d: 0 for d in SWIPE_DIRECTIONS}
    for resp in responses:
        direction = (resp.payload or {}).get("direction")
        if direction in dist:
            dist[direction] += 1
    return dist


def _vote_distribution(
    responses: list[ActivityResponse], config: dict | None
) -> dict[str, int]:
    dist = {key: 0 for key in _config_keys(config, "options")}
    for resp in responses:
        choice = (resp.payload or {}).get("choice")
        if isinstance(choice, str):
            dist[choice] = dist.get(choice, 0) + 1
    return dist


def _reaction_distribution(
    responses: list[ActivityResponse], config: dict | None
) -> dict[str, int]:
    dist = {key: 0 for key in _config_keys(config, "reactions")}
    for resp in responses:
        for entry in (resp.payload or {}).get("entries", []) or []:
            if not isinstance(entry, dict):
                continue
            reaction = entry.get("reaction")
            if isinstance(reaction, str):
                dist[reaction] = dist.get(reaction, 0) + 1
    return dist


def _distribution(
    fmt: str, responses: list[ActivityResponse], config: dict | None
) -> dict[str, int]:
    if fmt == "swipe":
        return _swipe_distribution(responses)
    if fmt == "vote":
        return _vote_distribution(responses, config)
    if fmt == "comment_reaction":
        return _reaction_distribution(responses, config)
    return {}


async def compute_activity_monitor_state(db, activity_id: uuid.UUID) -> dict:
    """Aggregate an activity's live monitor state.

    Returns ``{submission_count, distribution}`` where ``submission_count`` is the
    number of committed response ROWS (one per student, even for the stacking
    ``comment_reaction`` format) and ``distribution`` is the format-appropriate
    aggregate (see module docstring). A missing/soft-deleted activity yields an
    empty distribution rather than raising, so a best-effort broadcast never
    breaks the response write path.
    """
    activity = await db.get(Activity, activity_id)

    responses = (
        await db.execute(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == activity_id
            )
        )
    ).scalars().all()

    fmt = activity.format if activity is not None else ""
    config = activity.config if activity is not None else None

    return {
        "submission_count": len(responses),
        "distribution": _distribution(fmt, list(responses), config),
    }


async def _broadcast(db, activity_id: uuid.UUID, msg_type: str) -> None:
    payload = await compute_activity_monitor_state(db, activity_id)
    await monitor_manager.broadcast(
        str(activity_id), {"type": msg_type, **payload}
    )


async def broadcast_state(db, activity_id: uuid.UUID) -> None:
    """Broadcast the current aggregate state to every connected monitor."""
    await _broadcast(db, activity_id, "state")


async def broadcast_submission(db, activity_id: uuid.UUID) -> None:
    """Broadcast an updated aggregate after a student's response commits."""
    await _broadcast(db, activity_id, "submission")


async def broadcast_closed(db, activity_id: uuid.UUID) -> None:
    """Broadcast a terminal ``closed`` event with the final aggregate."""
    await _broadcast(db, activity_id, "closed")
