"""Canvas OAuth phase 1 models: per-user credentials, pending enrollments, sync events."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CanvasUserCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """OAuth credentials issued to a Meli user for a Canvas tenant.

    One row per Meli user — courses they link/join all reuse this credential.
    """

    __tablename__ = "canvas_user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    canvas_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    canvas_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(String(1000), nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(String(1000), nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class PendingEnrollment(UUIDPrimaryKeyMixin, Base):
    """A roster entry imported from Canvas for a user not yet on Meli.

    Claimed at first login by `app.api.deps.get_current_user`.
    """

    __tablename__ = "pending_enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "email", name="uq_pending_enrollments_course_email"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    canvas_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CanvasSyncEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only log of sync activity per course (roster diffs, file scans, errors)."""

    __tablename__ = "canvas_sync_events"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
