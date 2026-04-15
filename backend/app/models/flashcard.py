import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FlashcardFolder(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "flashcard_folders"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flashcard_folders.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class FlashcardSet(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "flashcard_sets"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flashcard_folders.id", ondelete="SET NULL"),
    )

    cards: Mapped[list["FlashcardCard"]] = relationship(
        back_populates="flashcard_set", cascade="all, delete-orphan",
        order_by="FlashcardCard.card_index"
    )
    source_documents: Mapped[list["FlashcardSetDocument"]] = relationship(
        cascade="all, delete-orphan"
    )


class FlashcardCard(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "flashcard_cards"

    flashcard_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flashcard_sets.id", ondelete="CASCADE"), nullable=False
    )
    card_index: Mapped[int] = mapped_column(Integer, nullable=False)
    front: Mapped[str] = mapped_column(String, nullable=False)
    back: Mapped[str] = mapped_column(String, nullable=False)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    flashcard_set: Mapped["FlashcardSet"] = relationship(back_populates="cards")


class FlashcardSetDocument(Base):
    __tablename__ = "flashcard_set_documents"

    flashcard_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flashcard_sets.id", ondelete="CASCADE"),
        primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True
    )


class FlashcardProgress(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "flashcard_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "flashcard_card_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    flashcard_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flashcard_cards.id", ondelete="CASCADE"),
        nullable=False
    )
    ease_factor: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("2.5"))
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    next_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # FSRS-5 state columns (null until first FSRS review). Stored as Numeric to
    # match the underlying DDL exactly and avoid spurious autogenerate diffs.
    stability: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    difficulty: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    last_grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fsrs_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
