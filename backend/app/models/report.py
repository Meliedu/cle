import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A course-scoped weekly / end-term report (spec §4.9, Decision 2).

    ONE ``reports`` table serves both audiences. ``audience`` ∈
    ``student|teacher``:

    * A **student-audience** row is a per-student weekly / end-term report and
      carries ``user_id`` — it is **owner-isolated via RLS** (enabled in the
      migration only, keyed on the ``app.current_user_id`` GUC, exactly like
      ``readiness_responses`` / ``work_item_progress`` / ``activity_responses``).
    * A **teacher course-level** row has ``user_id = NULL``. Because
      ``NULL = current_setting(...)::uuid`` is never true, the RLS predicate can
      never match it → it is invisible to every student; teacher access runs
      through the ``get_owned_course`` endpoint guard (Decision 2).

    ``period`` ∈ ``weekly|end_term``. ``status`` ∈
    ``draft|reviewed|sent|archived`` (default ``draft``). A report is drafted
    ONLY from reviewed learning notes and NEVER leaves ``draft`` without
    non-empty ``evidence_refs`` (spec §4.9 / Decision 1) — enforced at the job /
    endpoint layer (B3/B6), not by a table constraint. **NO SoftDeleteMixin** —
    a report is archived via ``status='archived'``, never soft-deleted.

    ``evidence_refs`` is a ``UUID[]`` of the reviewed ``LearningNote`` ids the
    body was drafted from. ``body`` is the typed JSONB section payload (summary /
    completed work / weak points / next actions / claim limits). ``export_history``
    is an append-only JSONB log (default ``[]``) of export events.
    """

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "audience IN ('student','teacher')",
            name="ck_reports_audience_valid",
        ),
        CheckConstraint(
            "period IN ('weekly','end_term')",
            name="ck_reports_period_valid",
        ),
        CheckConstraint(
            "status IN ('draft','reviewed','sent','archived')",
            name="ck_reports_status_valid",
        ),
        # Archive-list query support (teacher archive filters by these three).
        Index(
            "ix_reports_course_audience_period",
            "course_id",
            "audience",
            "period",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    audience: Mapped[str] = mapped_column(String(20), nullable=False)
    # NULL = teacher course-level row (Decision 2). Owner of a student-audience
    # row; the RLS policy (migration) isolates on this column.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    body: Mapped[dict | None] = mapped_column(JSONB)
    evidence_refs: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default=text("'draft'")
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    export_history: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
