import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AttendanceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A student's attendance at a single course meeting (spec §4.3).

    Student-owned row table (Decision 2): RLS owner-isolation on ``user_id`` is
    enabled in the migration only (never declared on the ORM). Attendance is
    **participation only** — it NEVER emits mastery evidence (doc rule). One row
    per ``(meeting_id, user_id)``; a repeat QR scan is an idempotent no-op.

    ``status`` is present|late|excused|absent; ``source`` is qr|manual_override.
    The override fields (``override_reason``/``override_by``) are populated only
    when a teacher manually overrides a scan and are NULL for QR check-ins.
    """

    __tablename__ = "attendance_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('present','late','excused','absent')",
            name="ck_attendance_records_status_valid",
        ),
        CheckConstraint(
            "source IN ('qr','manual_override')",
            name="ck_attendance_records_source_valid",
        ),
        UniqueConstraint(
            "meeting_id", "user_id", name="uq_attendance_records_meeting_user"
        ),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    override_reason: Mapped[str | None] = mapped_column(String)
    override_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    checked_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
