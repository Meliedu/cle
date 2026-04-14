import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CanvasIntegration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Link between a Meli course and a Canvas course.

    Phase 1: OAuth-backed. The per-course access token column was removed —
    sync uses the credential belonging to `connected_by_user_id` (usually the
    instructor who linked the course).
    """

    __tablename__ = "canvas_integrations"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    connected_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    canvas_course_id: Mapped[str] = mapped_column(String(100), nullable=False)
    canvas_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_roster_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_file_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(20), default="active")
    sync_config: Mapped[dict] = mapped_column(JSON, default=dict)
