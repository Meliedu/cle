import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        # The DEPLOYED constraint is
        #   pending | processing | ready | failed
        # and `pipeline.py` writes 'ready' on success. This model previously
        # listed 'completed' instead, so `Base.metadata.create_all` built a test
        # database that rejected the value production actually stores, and
        # accepted one production cannot. Both are allowed here: 'ready' so the
        # test schema matches production, 'completed' so the existing fixtures
        # that use it keep working. New code should write 'ready'.
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'completed', 'failed')",
            name="ck_documents_status_valid",
        ),
        CheckConstraint(
            "kind IN ('lecture','syllabus','reading','reference','other')",
            name="ck_documents_kind_valid",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    r2_key: Mapped[str] = mapped_column(String(500), nullable=False)
    r2_url: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # Typed, user-safe failure code (SourceFailureCode) set when status is
    # 'failed'. The UI maps this to copy; raw exception text never leaves the
    # structured logs. See app/services/failures.py.
    error_code: Mapped[str | None] = mapped_column(String(40))
    page_count: Mapped[int | None] = mapped_column(Integer)
    word_count: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    canvas_file_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    canvas_file_etag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="lecture")
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="SET NULL")
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="SET NULL")
    )
