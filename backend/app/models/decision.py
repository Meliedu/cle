import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class InstructorAlert(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "instructor_alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="ck_instructor_alerts_severity_valid",
        ),
        CheckConstraint(
            "status IN ('open','dismissed','resolved')",
            name="ck_instructor_alerts_status_valid",
        ),
        # Reframed in-place as the Review Case surface (CLE §5.4). The table
        # is NOT physically renamed; the alert_type list is broadened to cover
        # the Meli readiness/fit/skill review cases alongside the original 7.
        CheckConstraint(
            "alert_type IN ("
            "'student_disengaging','student_falling_behind',"
            "'cohort_concept_weakness','prereq_gap_for_upcoming_meeting',"
            "'low_quiz_participation','missed_deadline','content_gap',"
            "'readiness_gap','course_fit_concern','skill_gap'"
            ")",
            name="ck_instructor_alerts_alert_type_valid",
        ),
        Index(
            "uq_instructor_alerts_open_idempotent",
            "course_id",
            "alert_type",
            "target_user_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status = 'open'"),
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "idx_instructor_alerts_open",
            "instructor_id",
            "severity",
            text("created_at DESC"),
            postgresql_where=text("status = 'open'"),
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    instructor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    alert_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", server_default=text("''"),
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", server_default=text("'open'"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
    )
    # Review Case linkage into the evidence loop (CLE §5.4).
    linked_note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_notes.id", ondelete="SET NULL")
    )
    linked_follow_up_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("follow_up_actions.id", ondelete="SET NULL")
    )
    report_eligibility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
