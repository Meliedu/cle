import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CourseModule(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "course_modules"
    __table_args__ = (
        CheckConstraint("id <> parent_id", name="ck_course_modules_no_self_parent"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class CourseMeeting(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "course_meetings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','in_progress','taught','cancelled')",
            name="ck_course_meetings_status_valid",
        ),
        UniqueConstraint("course_id", "meeting_index", name="uq_course_meetings_course_index"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="SET NULL")
    )
    meeting_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    pre_meeting_briefing: Mapped[dict | None] = mapped_column(JSONB)
    post_meeting_summary: Mapped[dict | None] = mapped_column(JSONB)
    canvas_event_id: Mapped[str | None] = mapped_column(String(100))


class LearningObjective(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "learning_objectives"
    __table_args__ = (
        CheckConstraint(
            "NOT (module_id IS NOT NULL AND meeting_id IS NOT NULL)",
            name="ck_learning_objectives_scope_exclusive",
        ),
        CheckConstraint(
            "bloom_level IS NULL OR bloom_level IN "
            "('remember','understand','apply','analyze','evaluate','create')",
            name="ck_learning_objectives_bloom_valid",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="CASCADE")
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="CASCADE")
    )
    statement: Mapped[str] = mapped_column(String, nullable=False)
    bloom_level: Mapped[str | None] = mapped_column(String(20))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Assignment(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('essay','project','quiz','reading','presentation',"
            "'lab','problem_set','participation','other')",
            name="ck_assignments_kind_valid",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="SET NULL")
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    quiz_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="SET NULL")
    )
    canvas_assignment_id: Mapped[str | None] = mapped_column(String(100))
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class AssignmentSubmission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assignment_submissions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "user_id", name="uq_assignment_submissions_user"),
        CheckConstraint(
            "status IN ('not_started','in_progress','submitted','late','graded','excused')",
            name="ck_assignment_submissions_status_valid",
        ),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    feedback: Mapped[str | None] = mapped_column(String)
    submission_payload: Mapped[dict | None] = mapped_column(JSONB)
    canvas_submission_id: Mapped[str | None] = mapped_column(String(100))


class SyllabusImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "syllabus_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','parsed','applied','failed','superseded')",
            name="ck_syllabus_imports_status_valid",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    raw_text: Mapped[str] = mapped_column(String, nullable=False)
    parsed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
