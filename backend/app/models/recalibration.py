import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class RecalibrationStats(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "recalibration_stats"
    __table_args__ = (UniqueConstraint("pool_item_id"),)

    pool_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("revision_pool_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    llm_difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    hard_count: Mapped[int] = mapped_column(Integer, default=0)
    score_sum: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    score_sq_sum: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))


class RecalibrationModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "recalibration_models"
    __table_args__ = (UniqueConstraint("course_id", "content_type"),)

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dirichlet_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    transition_matrix: Mapped[dict] = mapped_column(JSONB, nullable=False)
    items_used: Mapped[int] = mapped_column(Integer, default=0)
    total_attempts_since_last_run: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
