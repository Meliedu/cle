import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ScoreCategory(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Teacher-defined score categories for the course (T024 score-policy step)."""

    __tablename__ = "score_categories"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    points_pool: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PronunciationScore(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pronunciation_scores"
    __table_args__ = (
        Index(
            "ix_pronunciation_scores_user_item",
            "user_id",
            "pronunciation_item_id",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    pronunciation_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pronunciation_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    target_text: Mapped[str] = mapped_column(String, nullable=False)
    audio_r2_key: Mapped[str | None] = mapped_column(String(500))
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    accuracy_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    fluency_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    completeness_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    prosody_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    detailed_result: Mapped[dict | None] = mapped_column(JSON)
    grading_provider: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StudentProgress(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "student_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    xp_points: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[date | None] = mapped_column(Date)
    quizzes_completed: Mapped[int] = mapped_column(Integer, default=0)
    flashcards_reviewed: Mapped[int] = mapped_column(Integer, default=0)
    speaking_sessions: Mapped[int] = mapped_column(Integer, default=0)
    badges: Mapped[dict] = mapped_column(JSON, default=list)
