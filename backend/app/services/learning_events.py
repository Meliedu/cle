"""Learning-event capture (OBJ-03).

A single immutable ``LearningEvent`` is written after every durable student
attempt (quiz / flashcard / revision / pronunciation). The event preserves
source, stage, actor, timestamp, and visibility per Core §3.6 so the
note-drafting step has a faithful signal to interpret.

``record_attempt_event`` constructs a fresh row and adds it to the caller's
session — it never mutates its inputs and never commits. The caller owns the
transaction (and, per the attempt endpoints, wraps this in a best-effort
try/except so a capture failure cannot roll back the durable attempt).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import LearningEvent


async def record_attempt_event(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
    user_id: uuid.UUID,
    source_kind: str,
    source_id: uuid.UUID | None,
    value: dict,
    stage: str = "review",
    event_type: str = "attempt",
    occurred_at: datetime | None = None,
    visibility_scope: str = "instructor",
) -> None:
    """Add an immutable ``LearningEvent`` for one attempt. Caller commits."""
    db.add(
        LearningEvent(
            course_id=course_id,
            user_id=user_id,
            source_kind=source_kind,
            source_id=source_id,
            stage=stage,
            event_type=event_type,
            value=dict(value),
            visibility_scope=visibility_scope,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )
    )
