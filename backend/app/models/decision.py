import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class NextAction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "next_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ("
            "'review_concept','prep_meeting','complete_assignment',"
            "'do_quiz','practice_weakness','catch_up_reading',"
            "'flashcard_review','pronunciation_practice','watch_recording'"
            ")",
            name="ck_next_actions_action_type_valid",
        ),
        CheckConstraint(
            "target_kind IS NULL OR target_kind IN ("
            "'concept','course_meeting','assignment','quiz',"
            "'flashcard_set','pronunciation_set','document','chunk'"
            ")",
            name="ck_next_actions_target_kind_valid",
        ),
        CheckConstraint(
            "candidate_source IN ('outer_fringe','deadline','review','fallback')",
            name="ck_next_actions_candidate_source_valid",
        ),
        # Mirror partial indexes from migration so create_all (test bootstrap)
        # reproduces production semantics.
        Index(
            "idx_next_actions_user_active",
            "user_id",
            text("priority_score DESC"),
            # ``now()`` not allowed in index predicates (STABLE, not IMMUTABLE);
            # mirrors the migration. Readers filter ``expires_at > now()`` at query time.
            postgresql_where=text("consumed_at IS NULL"),
        ),
        Index(
            "idx_next_actions_cleanup",
            "expires_at",
            postgresql_where=text("consumed_at IS NULL"),
        ),
        Index(
            "idx_next_actions_user_course",
            "user_id",
            "course_id",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE")
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    priority_score: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    candidate_source: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engine_variant: Mapped[str] = mapped_column(
        String(20), nullable=False, default="on", server_default=text("'on'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ActionOutcome(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "action_outcomes"
    __table_args__ = (
        CheckConstraint(
            "outcome_metric IS NULL OR outcome_metric IN "
            "('mastery_delta','quiz_score','recall','completion')",
            name="ck_action_outcomes_metric_valid",
        ),
        Index(
            "idx_action_outcomes_variant_served",
            "engine_variant",
            "served_at",
        ),
        Index(
            "idx_action_outcomes_user",
            "user_id",
            text("served_at DESC"),
        ),
        Index(
            "idx_action_outcomes_course_action",
            "course_id",
            "action_type",
        ),
    )

    next_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("next_actions.id", ondelete="SET NULL"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE")
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    engine_variant: Mapped[str] = mapped_column(String(20), nullable=False)
    served_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clicked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outcome_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    outcome_metric: Mapped[str | None] = mapped_column(String(40))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


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
        CheckConstraint(
            "alert_type IN ("
            "'student_disengaging','student_falling_behind',"
            "'cohort_concept_weakness','prereq_gap_for_upcoming_meeting',"
            "'low_quiz_participation','missed_deadline','content_gap'"
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EngineOverride(Base):
    __tablename__ = "engine_overrides"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('on','off')",
            name="ck_engine_overrides_mode_valid",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    set_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
