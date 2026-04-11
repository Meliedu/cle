import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class RevisionSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "revision_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_answered: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))


class RevisionPoolItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "revision_pool_items"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)

    # Quiz fields
    question_text: Mapped[str | None] = mapped_column(String)
    options: Mapped[dict | None] = mapped_column(JSON)
    correct_answer: Mapped[str | None] = mapped_column(String(10))
    explanation: Mapped[str | None] = mapped_column(String)

    # Flashcard fields
    front: Mapped[str | None] = mapped_column(String)
    back: Mapped[str | None] = mapped_column(String)

    # Speaking fields
    target_text: Mapped[str | None] = mapped_column(String)
    language: Mapped[str | None] = mapped_column(String(20))

    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Recalibration columns
    recalibrated_difficulty: Mapped[str | None] = mapped_column(String(10))
    recalibration_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    instructor_override: Mapped[bool] = mapped_column(Boolean, default=False)


class RevisionAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "revision_attempts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("revision_sessions.id", ondelete="CASCADE"), nullable=False
    )
    pool_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("revision_pool_items.id"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    time_taken_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    corrected_difficulty: Mapped[str | None] = mapped_column(String(10))


class RevisionItemServed(Base):
    __tablename__ = "revision_item_served"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    pool_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("revision_pool_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    served_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BanditModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bandit_models"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "content_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    weights: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    strategy: Mapped[str] = mapped_column(String(10), default="rules")
    reward_mean: Mapped[float] = mapped_column(Float, default=0.0)
    reward_var: Mapped[float] = mapped_column(Float, default=1.0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
