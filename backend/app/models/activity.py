import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Activity(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A course-scoped, teacher-authored in-class activity (spec §4.4).

    Operational — mirrors ``Checkpoint``/``WorkItem`` (Decision 3): **NO RLS**
    (every read is enrollment- or owner-guarded at the endpoint layer). Per-student
    submissions live in the separate owner-owned ``activity_responses`` table.

    ``format`` ∈ ``swipe|vote|comment_reaction`` (§4.4). ``status`` mirrors the
    checkpoint status machine (``draft|published|live|closed|archived``). The
    §4.5 publish-settings (``score_category_id``, ``points``, ``grading_mode``,
    ``late_rule``, ``score_bearing``, ``open_at``/``due_at``/``close_at``) ride on
    the activity so a score-bearing activity carries its own grade policy — the
    shared ``assert_score_policy_complete`` gate (B4) reads them duck-typed.
    ``config`` holds the format-specific renderable payload (swipe prompts / vote
    options / reaction set).
    """

    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint(
            "format IN ('swipe','vote','comment_reaction')",
            name="ck_activities_format_valid",
        ),
        CheckConstraint(
            "status IN ('draft','published','live','closed','archived')",
            name="ck_activities_status_valid",
        ),
        CheckConstraint(
            "grading_mode IS NULL OR grading_mode IN "
            "('auto','manual','participation')",
            name="ck_activities_grading_mode_valid",
        ),
        CheckConstraint(
            "late_rule IS NULL OR late_rule IN "
            "('accept_late','reject_late','accept_with_flag')",
            name="ck_activities_late_rule_valid",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="SET NULL")
    )
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default=text("'draft'")
    )
    open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonymous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # §4.5 publish-settings (all nullable until the teacher fills the score panel).
    score_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("score_categories.id", ondelete="SET NULL")
    )
    points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    grading_mode: Mapped[str | None] = mapped_column(String(20))
    late_rule: Mapped[str | None] = mapped_column(String(20))
    score_bearing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class ActivityResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single student's submission to one activity (spec §4.4).

    Student-owned row table (Decision 3): RLS owner-isolation on ``user_id`` is
    enabled in the migration only (never declared on the ORM) — the same shape as
    ``CheckpointResponse``/``WorkItemProgress``. Owner is ``user_id``; enforcement
    runs under the non-superuser ``meli_app`` role via the ``app.current_user_id``
    GUC. **NO soft-delete** — a student-owned participation row.

    One row per ``(activity_id, user_id)`` — a resubmit upserts in place;
    ``comment_reaction`` stacks multiple reactions INSIDE ``payload`` (§4.4).
    ``status`` is ``on_time``/``late`` derived at submission from the activity's
    ``close_at`` (mirrors ``CheckpointResponse``).
    """

    __tablename__ = "activity_responses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('on_time','late')",
            name="ck_activity_responses_status_valid",
        ),
        UniqueConstraint(
            "activity_id", "user_id", name="uq_activity_responses_activity_user"
        ),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
