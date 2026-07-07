import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """General **append-only** audit log (spec §8, Decision 4).

    Every audited action (``report.approve``/``report.send``/``report.export``,
    ``memory.decide``, ``checkpoint.publish`` …) appends exactly one row via
    ``services/audit.py::record_audit_event``. Mirrors the P5 ``grade_exports``
    append-only shape: UUID PK + a plain ``created_at`` only — **NO
    ``TimestampMixin`` (``updated_at``), NO ``SoftDeleteMixin`` (``deleted_at``),
    NO update/delete path.** ``grade_exports`` remains the CSV-export-specific log;
    ``audit_events`` is the general log the H4 coverage check enumerates.

    The ``actor_id`` FK deliberately carries **no ``ondelete``** (audit FK
    pattern): an audit trail must survive even if the acting user is later
    removed — deletion is left to the default (RESTRICT), so the log is never
    silently orphaned or cascaded away.

    Reserved-name note: ``metadata`` is a reserved attribute on the Declarative
    ``Base`` (it holds the table registry). The Python attribute is therefore
    named ``event_metadata`` and mapped to the ``"metadata"`` DB column so the
    stored/queryable column name still matches the spec (``metadata JSONB``).
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        # Course-scoped audit lookups (the H4 coverage check + per-course review).
        Index("ix_audit_events_course_id", "course_id"),
        # Per-target history ("show me everything that happened to this report").
        Index("ix_audit_events_target", "target_kind", "target_id"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    # No ondelete — audit FK pattern: the trail outlives the actor.
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Mapped to the "metadata" DB column — see the reserved-name note above.
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
