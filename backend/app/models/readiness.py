"""Readiness funnel model (spec §4.7).

``readiness_responses`` is the FIRST student-owned row table in this build, so
RLS lands with its migration (Decision 2; pattern ``28236be3d7b3``). The owner
is ``user_id``; the migration enables ROW LEVEL SECURITY + an owner-isolation
policy on the ``app.current_user_id`` GUC. ORM models never declare RLS — it
lives only in the migration.

The ``phase`` CHECK accepts all four spec §4.7 values (forward-compatible per
Decision 4): CLE ships only ``eligibility_survey`` + ``ready_check`` question
sets today, but ``diagnostic`` (optional/skippable) and ``recommendation``
(computed server-side) are valid phases so a future placement test needs no
schema change. Answers/result are JSONB; unique on ``(user, course, phase)`` so
a resubmit upserts the latest (Task 3).
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReadinessResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "readiness_responses"
    __table_args__ = (
        CheckConstraint(
            "phase IN ('eligibility_survey','ready_check','diagnostic','recommendation')",
            name="ck_readiness_responses_phase_valid",
        ),
        CheckConstraint(
            "status IN ('in_progress','completed')",
            name="ck_readiness_responses_status_valid",
        ),
        UniqueConstraint(
            "user_id", "course_id", "phase", name="uq_readiness_user_course_phase",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(30), nullable=False)
    answers: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_progress",
        server_default=text("'in_progress'"),
    )
