import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
        CheckConstraint(
            "description IS NULL OR length(description) <= 2000",
            name="ck_concepts_description_length",
        ),
        CheckConstraint(
            "length(name) <= 255",
            name="ck_concepts_name_length",
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


class ConceptMastery(Base):
    __tablename__ = "concept_mastery"
    __table_args__ = (
        CheckConstraint("alpha > 0", name="ck_concept_mastery_alpha_pos"),
        CheckConstraint("beta > 0", name="ck_concept_mastery_beta_pos"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_concept_mastery_confidence_range",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    alpha: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, default=Decimal("1.000")
    )
    beta: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, default=Decimal("1.000")
    )
    # GENERATED STORED column — read-only on the SQLAlchemy side. The
    # Computed() makes Base.metadata.create_all (used by the test bootstrap)
    # mirror the production migration's GENERATED column definition.
    mastery_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        Computed("alpha / (alpha + beta)", persisted=True),
        nullable=False,
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("0.000")
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_correct_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_decay_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConceptMasteryHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "concept_mastery_history"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('attempt','decay','replay','reset')",
            name="ck_concept_mastery_history_event_type_valid",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    alpha: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    beta: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_kind: Mapped[str | None] = mapped_column(String(20))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    outcome: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
