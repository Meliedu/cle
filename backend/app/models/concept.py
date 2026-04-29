import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Concept(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "concepts"
    __table_args__ = (
        CheckConstraint("id <> canonical_id", name="ck_concepts_no_self_canonical"),
        CheckConstraint(
            "status IN ('pending','approved','rejected','merged')",
            name="ck_concepts_status_valid",
        ),
        # Mirror the partial functional unique index from the migration so that
        # Base.metadata.create_all (used by the test bootstrap) builds the same
        # unique constraint the production schema enforces.
        Index(
            "uq_concepts_course_lower_name",
            "course_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND canonical_id IS NULL"),
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    canonical_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="SET NULL")
    )
    embedding = mapped_column(Vector(3072))
    extracted_from_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    instructor_curated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ConceptPrerequisite(Base):
    __tablename__ = "concept_prerequisites"
    __table_args__ = (
        CheckConstraint(
            "prereq_concept_id <> dependent_concept_id",
            name="ck_concept_prerequisites_no_self",
        ),
        CheckConstraint(
            "strength >= 0 AND strength <= 1",
            name="ck_concept_prerequisites_strength_range",
        ),
    )

    prereq_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dependent_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    strength: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.00")
    )
    instructor_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConceptTag(Base):
    __tablename__ = "concept_tags"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('chunk','question','flashcard_card','pronunciation_item',"
            "'pool_item','objective','meeting','assignment')",
            name="ck_concept_tags_target_kind_valid",
        ),
        CheckConstraint(
            "weight >= 0 AND weight <= 1",
            name="ck_concept_tags_weight_range",
        ),
        CheckConstraint(
            "role IS NULL OR (target_kind = 'meeting' AND "
            "role IN ('introduced','covered','reinforced'))",
            name="ck_concept_tags_role_for_meeting",
        ),
    )

    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    target_kind: Mapped[str] = mapped_column(String(30), primary_key=True)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    weight: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.00")
    )
    role: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
