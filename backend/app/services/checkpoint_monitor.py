"""Live monitor hub for checkpoints (P3 T12, Decision 4).

REUSE — NOT rebuild. The teacher live-monitor WebSocket rides the SAME
``ConnectionManager`` class that powers the live-quiz hub (``live_quiz.py``); we
only instantiate a second module-level ``monitor_manager`` so checkpoint monitor
connections live in their own namespace, keyed by ``str(checkpoint_id)``.

Message shapes (all JSON, ``send_text`` under the hood):
- On connect, the handler sends ``{type: "state", submission_count,
  confidence_distribution}`` to the newly-connected socket only.
- ``broadcast_submission`` pushes ``{type: "submission", ...}`` to every
  connected monitor after a student's response commits (the T7 seam).
- ``broadcast_closed`` pushes ``{type: "closed", ...}`` when the checkpoint
  closes (the T5 close endpoint and, later, the T13 cron).

``confidence_distribution`` is the checkpoint-wide −2..+2 histogram of
``review_point`` confidences (final-comments carry no confidence), mirroring the
T6 ``/results`` aggregation.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.models.checkpoint import CheckpointResponse
from app.services.live_quiz import ConnectionManager

logger = logging.getLogger(__name__)

#: The −2..+2 ConfidenceScale buckets; every bucket is zero-filled so the
#: monitor histogram renders a stable axis (matches ``checkpoints.py``).
CONFIDENCE_BUCKETS: tuple[int, ...] = (-2, -1, 0, 1, 2)

#: Second instance of the live-quiz hub class — no new WS framework (Decision 4).
monitor_manager = ConnectionManager()


async def compute_monitor_state(db, checkpoint_id: uuid.UUID) -> dict:
    """Aggregate a checkpoint's live monitor state.

    Returns ``{submission_count, confidence_distribution}`` where
    ``submission_count`` is the total number of committed responses and
    ``confidence_distribution`` is the −2..+2 histogram of review-point
    confidences (non-confidence responses are counted only toward the total).
    """
    responses = (
        await db.execute(
            select(CheckpointResponse).where(
                CheckpointResponse.checkpoint_id == checkpoint_id
            )
        )
    ).scalars().all()

    distribution = {str(b): 0 for b in CONFIDENCE_BUCKETS}
    for resp in responses:
        if resp.confidence is not None:
            key = str(resp.confidence)
            if key in distribution:
                distribution[key] += 1

    return {
        "submission_count": len(responses),
        "confidence_distribution": distribution,
    }


async def _broadcast(db, checkpoint_id: uuid.UUID, msg_type: str) -> None:
    payload = await compute_monitor_state(db, checkpoint_id)
    await monitor_manager.broadcast(
        str(checkpoint_id), {"type": msg_type, **payload}
    )


async def broadcast_state(db, checkpoint_id: uuid.UUID) -> None:
    """Broadcast the current aggregate state to every connected monitor."""
    await _broadcast(db, checkpoint_id, "state")


async def broadcast_submission(db, checkpoint_id: uuid.UUID) -> None:
    """Broadcast an updated aggregate after a student's response commits."""
    await _broadcast(db, checkpoint_id, "submission")


async def broadcast_closed(db, checkpoint_id: uuid.UUID) -> None:
    """Broadcast a terminal ``closed`` event with the final aggregate."""
    await _broadcast(db, checkpoint_id, "closed")
