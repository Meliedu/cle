import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    JSON,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Course(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        # Course Context Package approval gate (CLE §6.5): touchpoints / note
        # drafting are released only once the context is ``approved``.
        CheckConstraint(
            "context_status IN ('draft','approved')",
            name="ck_courses_context_status_valid",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    semester: Mapped[str | None] = mapped_column(String(20))
    instructor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    enroll_code: Mapped[str] = mapped_column(
        String(16), nullable=False, unique=True, index=True
    )
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    context_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default=text("'draft'")
    )
    context_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    instructor: Mapped["User"] = relationship("User", lazy="selectin")
    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Enrollment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "user_id"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    course: Mapped["Course"] = relationship(back_populates="enrollments")
    user: Mapped["User"] = relationship("User", lazy="selectin")
