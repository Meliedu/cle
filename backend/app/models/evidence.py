"""Meli reviewed-evidence loop models (Core OBJ-03..09, CLE §5.2).

Governing rule (Core §0.2 / §7): "AI drafts and suggests. Instructors review
meaning and action. Reviewed evidence becomes course memory and report output."

These tables are CORE-GENERIC — no CLE-specific fields (skill_category, HSK,
audio). Every partial / unique index is mirrored in ``__table_args__`` so the
test bootstrap's ``Base.metadata.create_all`` reproduces the production schema
defined by the companion migration.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class LearningEvent(UUIDPrimaryKeyMixin, Base):
    """OBJ-03 — immutable record of a student signal.

    Preserves source, stage, actor, timestamp, and visibility (Core §3.6).
    """

    __tablename__ = "learning_events"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('entry','before_class','during_class','after_class','review')",
            name="ck_learning_events_stage_valid",
        ),
        CheckConstraint(
            "visibility_scope IN ('student','instructor','course_team')",
            name="ck_learning_events_visibility_scope_valid",
        ),
        Index(
            "idx_learning_events_course_user_time",
            "course_id",
            "user_id",
            text("occurred_at DESC"),
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    visibility_scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="instructor",
        server_default=text("'instructor'"),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LearningNote(UUIDPrimaryKeyMixin, Base):
    """OBJ-04 — AI-drafted interpretation of one or more learning events.

    Stays ``draft`` until an instructor ReviewAction promotes it (Core §5.2).
    ``user_id`` NULL denotes a cohort-level note.
    """

    __tablename__ = "learning_notes"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ("
            "'draft','queued','reviewed','edited','merged','split','archived'"
            ")",
            name="ck_learning_notes_review_status_valid",
        ),
        Index("idx_learning_notes_course_status", "course_id", "review_status"),
        Index("idx_learning_notes_course_user", "course_id", "user_id"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    source_event_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    context_anchor: Mapped[dict | None] = mapped_column(JSONB)
    evidence_category: Mapped[str | None] = mapped_column(String(40))
    observed_signal: Mapped[str] = mapped_column(Text, nullable=False)
    draft_interpretation: Mapped[str | None] = mapped_column(Text)
    limitation_note: Mapped[str | None] = mapped_column(Text)
    suggested_follow_up: Mapped[dict | None] = mapped_column(JSONB)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default=text("'draft'")
    )
    outcome_status: Mapped[str | None] = mapped_column(String(20))
    report_eligibility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReviewAction(UUIDPrimaryKeyMixin, Base):
    """OBJ-06 — append-only record of instructor judgment on a note (Core §5.2)."""

    __tablename__ = "review_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ("
            "'accept','edit','merge','split','assign_followup',"
            "'archive','carry_forward','mark_resolved'"
            ")",
            name="ck_review_actions_action_type_valid",
        ),
        Index(
            "idx_review_actions_note_time",
            "learning_note_id",
            text("created_at DESC"),
        ),
    )

    learning_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_role: Mapped[str] = mapped_column(String(20), nullable=False)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    prior_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))
    edit_text: Mapped[str | None] = mapped_column(Text)
    report_eligibility_change: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FollowUpAction(UUIDPrimaryKeyMixin, Base):
    """OBJ-07 — a reviewed follow-up assigned to a student (Core §B)."""

    __tablename__ = "follow_up_actions"
    __table_args__ = (
        CheckConstraint(
            "assignment_status IN ("
            "'suggested','assigned','viewed','completed',"
            "'checked','closed','carried_forward'"
            ")",
            name="ck_follow_up_actions_assignment_status_valid",
        ),
        Index(
            "idx_follow_up_actions_user_course_status",
            "user_id",
            "course_id",
            "assignment_status",
        ),
        Index(
            "idx_follow_up_actions_course_status",
            "course_id",
            "assignment_status",
        ),
    )

    learning_note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_notes.id", ondelete="CASCADE")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assignment_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="suggested",
        server_default=text("'suggested'"),
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Audit reference — no ondelete; user deletion is blocked while rows
    # reference them. Matches the project-wide audit FK pattern.
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutcomeCheck(UUIDPrimaryKeyMixin, Base):
    """OBJ-08 — did the follow-up move the signal? (CLE §5.5).

    Partial-unique on ``follow_up_action_id`` mirrors the old action_outcomes
    idempotency pattern so a follow-up gets at most one closing outcome.
    """

    __tablename__ = "outcome_checks"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending','completed','improved','persistent',"
            "'resolved','needs_review','carried_forward'"
            ")",
            name="ck_outcome_checks_status_valid",
        ),
        Index(
            "uq_outcome_checks_followup",
            "follow_up_action_id",
            unique=True,
            postgresql_where=text("follow_up_action_id IS NOT NULL"),
        ),
        Index("idx_outcome_checks_course_user", "course_id", "user_id"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    learning_note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_notes.id", ondelete="CASCADE")
    )
    follow_up_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("follow_up_actions.id", ondelete="CASCADE")
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_events.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default=text("'pending'")
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CourseRecordItem(UUIDPrimaryKeyMixin, Base):
    """OBJ-09 — durable, reviewed course memory entry (Core §5.4)."""

    __tablename__ = "course_record_items"
    __table_args__ = (
        Index(
            "idx_course_record_items_course_time",
            "course_id",
            text("created_at DESC"),
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    learning_note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_notes.id", ondelete="SET NULL")
    )
    relationship_summary: Mapped[dict | None] = mapped_column(JSONB)
    action_summary: Mapped[dict | None] = mapped_column(JSONB)
    outcome_summary: Mapped[dict | None] = mapped_column(JSONB)
    instructor_comment: Mapped[str | None] = mapped_column(Text)
    carry_forward: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    report_history: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
