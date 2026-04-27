import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PronunciationFolder(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "pronunciation_folders"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pronunciation_folders.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class PronunciationSet(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "pronunciation_sets"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pronunciation_folders.id", ondelete="SET NULL"),
    )
    difficulty: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)

    items: Mapped[list["PronunciationItem"]] = relationship(
        back_populates="pronunciation_set",
        cascade="all, delete-orphan",
        order_by="PronunciationItem.item_index",
    )
    source_documents: Mapped[list["PronunciationSetDocument"]] = relationship(
        cascade="all, delete-orphan"
    )


class PronunciationItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pronunciation_items"
    __table_args__ = (
        Index(
            "ix_pronunciation_items_set_idx",
            "pronunciation_set_id",
            "item_index",
        ),
    )

    pronunciation_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pronunciation_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    phonetic: Mapped[str | None] = mapped_column(String(500))
    translation: Mapped[str | None] = mapped_column(String(1000))
    tips: Mapped[str | None] = mapped_column(String(2000))
    item_type: Mapped[str] = mapped_column(String(10), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pronunciation_set: Mapped["PronunciationSet"] = relationship(back_populates="items")


class PronunciationSetDocument(Base):
    __tablename__ = "pronunciation_set_documents"

    pronunciation_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pronunciation_sets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
