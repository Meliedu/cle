import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SchedulerModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-user-per-course FSRS parameter store and strategy tracker."""

    __tablename__ = "scheduler_models"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id"),
        Index("ix_scheduler_models_course_id", "course_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    # 19 FSRS-5 learnable parameters stored as JSONB list[float]
    parameters: Mapped[list[float]] = mapped_column(
        JSONB, nullable=False
    )
    # "sm2" until SWITCHOVER_THRESHOLD reviews, then "fsrs"
    strategy: Mapped[str] = mapped_column(String(10), nullable=False, default="sm2")
    # Total review count across all cards for this user/course
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
