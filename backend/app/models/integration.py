import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CanvasIntegration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canvas_integrations"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    canvas_course_id: Mapped[str] = mapped_column(String(100), nullable=False)
    canvas_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(String(500))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(20), default="idle")
    sync_config: Mapped[dict] = mapped_column(JSON, default=dict)
