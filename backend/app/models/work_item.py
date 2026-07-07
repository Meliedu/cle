import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class WorkItem(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A single row on a course's checklist spine (spec §4.6).

    Course-scoped, teacher-authored, **operational** — mirrors
    ``CheckpointLaunch`` (Decision 2): **NO RLS** on this table (every read is
    enrollment- or owner-guarded at the endpoint layer). Per-student state lives
    in the separate owner-owned ``work_item_progress`` table (B2).

    ``source_kind`` ships the FULL spec §4.6 enum now
    (``checkpoint|practice|quiz|activity|material|follow_up|report``) so no later
    widening is needed; P4 only WRITES ``checkpoint`` (publish path) and
    ``material`` (assign-to-session). ``meeting`` is deliberately NOT a
    ``source_kind`` — sessions live in ``course_meetings`` and feed the calendar
    directly (Decision 1). ``source_id`` points at the originating artifact
    (a checkpoint id, a document id, …).

    A UNIQUE index on ``(course_id, source_kind, source_id)`` makes the publish +
    backfill upsert idempotent via ``on_conflict_do_nothing`` (Decision 3) — a
    re-publish or the backfill can never double-insert.
    """

    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('checkpoint','practice','quiz','activity',"
            "'material','follow_up','report')",
            name="ck_work_items_source_kind_valid",
        ),
        # Idempotency key for the publish/backfill upsert (Decision 3).
        Index(
            "uq_work_items_course_source",
            "course_id",
            "source_kind",
            "source_id",
            unique=True,
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    score_bearing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    visible_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


class WorkItemProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single student's state for one checklist item (spec §4.6).

    Student-owned row table (Decision 2): RLS owner-isolation on ``user_id`` is
    enabled in the migration only (never declared on the ORM) — the same shape
    as ``CheckpointResponse``. Owner is ``user_id``; enforcement runs under the
    non-superuser ``meli_app`` role via the ``app.current_user_id`` GUC.

    ``status`` ships the FULL spec §4.6 lifecycle now
    (``pending|in_progress|submitted|late|missed|completed|follow_up_assigned``)
    so no later widening is needed. One row per ``(work_item_id, user_id)`` — a
    state transition upserts in place (Decision 3).
    """

    __tablename__ = "work_item_progress"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','in_progress','submitted','late',"
            "'missed','completed','follow_up_assigned')",
            name="ck_work_item_progress_status_valid",
        ),
        UniqueConstraint(
            "work_item_id", "user_id", name="uq_work_item_progress_item_user"
        ),
    )

    work_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
