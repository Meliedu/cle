import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class QuizFolder(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "quiz_folders"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_folders.id", ondelete="SET NULL")
    )
    purpose: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="live"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class Quiz(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "quizzes"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    quiz_type: Mapped[str] = mapped_column(String(20), default="practice")
    purpose: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="after_class"
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_folders.id", ondelete="SET NULL")
    )
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- P5 publish-settings (Decision 1) ---
    # NEW dedicated practice-vs-graded axis. NOT the existing `purpose`
    # (after_class|live) or the unconstrained legacy `quiz_type`. Every existing
    # quiz backfills to 'practice' via server_default.
    assessment_purpose: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="practice"
    )
    score_bearing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    score_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("score_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    grading_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    open_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    close_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    late_rule: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "assessment_purpose IN ('practice','graded')",
            name="ck_quizzes_assessment_purpose_valid",
        ),
        CheckConstraint(
            "grading_mode IN ('auto','manual','participation')",
            name="ck_quizzes_grading_mode_valid",
        ),
        CheckConstraint(
            "late_rule IN ('accept_late','reject_late','accept_with_flag')",
            name="ck_quizzes_late_rule_valid",
        ),
    )

    questions: Mapped[list["Question"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", order_by="Question.question_index"
    )
    source_documents: Mapped[list["QuizDocument"]] = relationship(
        cascade="all, delete-orphan"
    )


class Question(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(30), default="multiple_choice")
    question_text: Mapped[str] = mapped_column(String, nullable=False)
    options: Mapped[dict | None] = mapped_column(JSON)
    correct_answer: Mapped[str] = mapped_column(String, nullable=False)
    explanation: Mapped[str | None] = mapped_column(String)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")


class QuizDocument(Base):
    __tablename__ = "quiz_documents"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )


class QuizAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "quiz_attempts"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # When an attempt was created by a live quiz session ending, this holds
    # the session id. A unique index on (user_id, live_session_id) prevents
    # double-awarding XP / duplicate attempts if the end-session hook fires
    # more than once (host double-click, WS + REST path, etc).
    live_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    answers: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    total_questions: Mapped[int | None] = mapped_column(Integer)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    time_taken_seconds: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
