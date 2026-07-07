"""Student checkpoint-response submission + the evidence seam (P3 T7).

This is the ONE evidence path for checkpoints (Decision 5 — no parallel
system). It mirrors ``api/quizzes.py`` exactly:

1. Persist the student's answer (an upsert on ``(card_id, user_id)`` so a
   resubmit updates in place), commit — the answer is now durable.
2. Best-effort evidence seam (wrapped in try/except so a failure here can
   never roll back the committed answer): write a single ``LearningEvent``
   (``stage='during_class'``, ``source_kind='checkpoint_card'``) and, for a
   ``review_point`` card, enqueue an ``update_concept_mastery`` Task with
   ``outcome=(confidence+2)/4``. ``final_comments`` text carries no mastery
   signal, so it never enqueues.
3. Notify the live monitor (a no-op seam until T12 wires the WS hub).

The caller (endpoint) resolves + authorizes the checkpoint/card and passes the
authenticated ``user_id`` — the student can only ever write their own row, so
"wrong-owner cannot write" holds at the app layer (RLS is defense-in-depth).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkpoint import Checkpoint, CheckpointCard, CheckpointResponse
from app.models.task import Task
from app.services.learning_events import record_attempt_event

logger = logging.getLogger(__name__)

#: Checkpoint statuses that accept a student intro / submission (§4.2). A
#: checkpoint is answerable while it is live to students.
OPEN_STATUSES: frozenset[str] = frozenset({"published", "live"})

#: The confidence scale bounds (pilot ``ConfidenceScale``, −2..+2). Kept here so
#: the outcome normalization has a single source.
CONFIDENCE_MIN = -2
CONFIDENCE_MAX = 2


def confidence_to_outcome(confidence: int) -> float:
    """Normalize a −2..+2 confidence to a 0..1 mastery outcome: ``(c+2)/4``."""
    span = CONFIDENCE_MAX - CONFIDENCE_MIN
    return (confidence - CONFIDENCE_MIN) / span


def is_within_window(cp: Checkpoint, now: datetime) -> bool:
    """Whether ``now`` falls inside the checkpoint's release..close window.

    A ``None`` bound is open-ended on that side (``release_at`` unset = already
    released; ``close_at`` unset = closes only by rule/manual action).
    """
    if cp.release_at is not None and now < cp.release_at:
        return False
    if cp.close_at is not None and now > cp.close_at:
        return False
    return True


def _invalid_response(message: str) -> HTTPException:
    """A 422 for a card/answer-shape mismatch (confidence vs text)."""
    return HTTPException(
        status_code=422,
        detail={"code": "INVALID_RESPONSE", "message": message},
    )


def _validate_shape(
    card: CheckpointCard, confidence: int | None, text_response: str | None
) -> tuple[int | None, str | None]:
    """Enforce confidence-on-review / text-on-final; return normalized pair."""
    if card.kind == "review_point":
        if confidence is None:
            raise _invalid_response(
                "A confidence rating is required for a review point."
            )
        if text_response is not None:
            raise _invalid_response(
                "A review point takes a confidence rating, not a text answer."
            )
        return confidence, None
    # final_comments
    if text_response is None or not text_response.strip():
        raise _invalid_response(
            "A comment is required for the final comments card."
        )
    if confidence is not None:
        raise _invalid_response(
            "The final comments card does not take a confidence rating."
        )
    return None, text_response


async def _notify_monitor(db: AsyncSession, checkpoint_id: uuid.UUID) -> None:
    """Live-monitor broadcast seam (Decision 4, wired in T12).

    Pushes a ``submission`` broadcast to any connected teacher monitor via the
    reused live-quiz ``ConnectionManager`` (``monitor_manager``). Best-effort:
    a broadcast failure must NEVER fail the student's already-committed answer,
    so the whole thing is wrapped. Imported lazily to keep the module's import
    graph flat and side-effect free.
    """
    try:
        from app.services.checkpoint_monitor import broadcast_submission

        await broadcast_submission(db, checkpoint_id)
    except Exception:  # noqa: BLE001 — non-fatal: response already persisted
        logger.exception(
            "Failed to broadcast checkpoint submission to monitor for "
            "checkpoint_id=%s",
            checkpoint_id,
        )


async def submit_checkpoint_response(
    db: AsyncSession,
    *,
    checkpoint: Checkpoint,
    card: CheckpointCard,
    user_id: uuid.UUID,
    confidence: int | None,
    text_response: str | None,
) -> CheckpointResponse:
    """Upsert one checkpoint response and fire the evidence seam.

    The caller has already resolved+authorized ``checkpoint``/``card`` and
    verified the card belongs to the checkpoint.
    """
    confidence, text_response = _validate_shape(card, confidence, text_response)

    # Capture identifiers up front: a best-effort rollback below expires the
    # ORM instances, so any later attribute access would trigger lazy async IO
    # (MissingGreenlet). Locals are immune.
    checkpoint_id = checkpoint.id
    course_id = checkpoint.course_id
    card_id = card.id
    card_kind = card.kind

    now = datetime.now(timezone.utc)
    # Past close_at ⇒ late (a manual-close checkpoint stays answerable while
    # published/live, but the row records that it arrived after the window).
    row_status = (
        "late"
        if checkpoint.close_at is not None and now > checkpoint.close_at
        else "on_time"
    )

    # Upsert on the (card_id, user_id) unique constraint — a resubmit updates
    # in place (id is set explicitly because a Core INSERT does not fire the
    # Python-side ``default=uuid.uuid4``).
    stmt = (
        pg_insert(CheckpointResponse)
        .values(
            id=uuid.uuid4(),
            checkpoint_id=checkpoint_id,
            card_id=card_id,
            user_id=user_id,
            confidence=confidence,
            text_response=text_response,
            status=row_status,
            submitted_at=now,
        )
        .on_conflict_do_update(
            index_elements=["card_id", "user_id"],
            set_={
                "confidence": confidence,
                "text_response": text_response,
                "status": row_status,
                "submitted_at": now,
                "updated_at": now,
            },
        )
        .returning(CheckpointResponse.id)
    )
    response_id = (await db.execute(stmt)).scalar_one()
    await db.commit()

    # Evidence seam (best-effort) — a failure here must not lose the answer.
    try:
        if card_kind == "review_point":
            outcome = confidence_to_outcome(confidence)  # type: ignore[arg-type]
            db.add(
                Task(
                    task_type="update_concept_mastery",
                    payload={
                        "user_id": str(user_id),
                        "course_id": str(course_id),
                        "target_kind": "checkpoint_card",
                        "target_id": str(card_id),
                        "outcome": outcome,
                        "attempt_kind": "checkpoint",
                    },
                    status="pending",
                )
            )
            value: dict = {"confidence": confidence, "card_kind": card_kind}
        else:
            value = {"text": text_response, "card_kind": card_kind}
        await record_attempt_event(
            db,
            course_id=course_id,
            user_id=user_id,
            source_kind="checkpoint_card",
            source_id=card_id,
            stage="during_class",
            value=value,
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — non-fatal: response already persisted
        logger.exception(
            "Failed to record checkpoint evidence for checkpoint_id=%s "
            "card_id=%s user_id=%s",
            checkpoint_id,
            card_id,
            user_id,
        )
        await db.rollback()

    await _notify_monitor(db, checkpoint_id)

    response = await db.get(CheckpointResponse, response_id)
    assert response is not None
    return response
