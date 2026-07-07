import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Checkpoint(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "checkpoints"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('session','follow_up')", name="ck_checkpoints_kind_valid"
        ),
        # Full spec §4.2 status machine so P3 needs no widening; P1 only WRITES
        # draft/teacher_editing (enforced in the service layer, not the DB).
        CheckConstraint(
            "status IN ('draft','teacher_editing','approved','scheduled',"
            "'published','live','closed','archived')",
            name="ck_checkpoints_status_valid",
        ),
        CheckConstraint(
            "close_rule IS NULL OR close_rule IN "
            "('manual','at_close_at','end_of_session')",
            name="ck_checkpoints_close_rule_valid",
        ),
        CheckConstraint(
            "carried_from_id IS NULL OR id <> carried_from_id",
            name="ck_checkpoints_no_self_carry",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default=text("'draft'")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_rule: Mapped[str | None] = mapped_column(String(20))
    qr_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    carried_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoints.id", ondelete="SET NULL")
    )
    generation_meta: Mapped[dict | None] = mapped_column(JSONB)


class CheckpointCard(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "checkpoint_cards"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('review_point','final_comments')",
            name="ck_checkpoint_cards_kind_valid",
        ),
        CheckConstraint(
            "removed_reason IS NULL OR removed_reason IN "
            "('not_needed','duplicate','not_covered','other')",
            name="ck_checkpoint_cards_removed_reason_valid",
        ),
        # Exactly one non-removed final_comments card per checkpoint (§4.2:
        # fixed, not removable). Partial unique index mirrors the migration.
        Index(
            "uq_checkpoint_cards_one_final",
            "checkpoint_id",
            unique=True,
            postgresql_where=text("kind = 'final_comments' AND deleted_at IS NULL"),
        ),
    )

    checkpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("checkpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    objective_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_objectives.id", ondelete="SET NULL")
    )
    removed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    removed_reason: Mapped[str | None] = mapped_column(String(20))
    removed_note: Mapped[str | None] = mapped_column(String)


class CheckpointResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A student's answer to a single checkpoint card (spec §4.2).

    Student-owned row table (Decision 2): RLS owner-isolation on ``user_id`` is
    enabled in the migration only (never declared on the ORM). ``confidence`` is
    the −2..+2 scale and is NULL for ``final_comments`` cards (which carry
    ``text_response`` instead); ``status`` is ``on_time``/``late`` derived at
    submission from the checkpoint close time. One row per ``(card_id, user_id)``
    — a resubmit upserts in place.
    """

    __tablename__ = "checkpoint_responses"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN -2 AND 2",
            name="ck_checkpoint_responses_confidence_range",
        ),
        CheckConstraint(
            "status IN ('on_time','late')",
            name="ck_checkpoint_responses_status_valid",
        ),
        UniqueConstraint(
            "card_id", "user_id", name="uq_checkpoint_responses_card_user"
        ),
    )

    checkpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("checkpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("checkpoint_cards.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    confidence: Mapped[int | None] = mapped_column(Integer)
    text_response: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
