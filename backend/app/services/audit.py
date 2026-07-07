"""Append-only audit write helper (P7 Task B2, Decision 4).

``record_audit_event`` appends exactly one ``audit_events`` row for an audited
action (report approve/send/export, memory decide, checkpoint publish, …). It is
a pure, transactional building block with **NO commit inside** — the endpoint /
job caller owns the commit, mirroring ``services/work_items.py`` ("caller owns
commit"). Being append-only, it NEVER upserts: a second call always writes a
second row.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent


async def record_audit_event(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
    actor_id: uuid.UUID,
    event_type: str,
    target_kind: str,
    target_id: uuid.UUID,
    metadata: dict | None = None,
) -> AuditEvent:
    """Append one audit row for ``(course, actor, event_type, target)``.

    Append-only: every call creates a fresh row (never an upsert). ``metadata``
    is stored in the ``audit_events.metadata`` JSONB column (the ORM attribute is
    ``event_metadata`` — ``metadata`` is reserved on the Declarative ``Base``).

    Pure helper: the caller owns the commit — durability rides the caller's
    surrounding transaction so the audit row lands atomically with the mutation
    it records.
    """
    event = AuditEvent(
        course_id=course_id,
        actor_id=actor_id,
        event_type=event_type,
        target_kind=target_kind,
        target_id=target_id,
        event_metadata=metadata,
    )
    db.add(event)
    return event
