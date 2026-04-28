"""phase 2 concepts + prerequisites + polymorphic tags

Revision ID: e7c4a9b1f2d8
Revises: d8c3a1e7f9b4
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e7c4a9b1f2d8"
down_revision: Union[str, None] = "d8c3a1e7f9b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- concepts ----------
    op.create_table(
        "concepts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("canonical_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float), nullable=True),  # placeholder; replaced below
        sa.Column("extracted_from_chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("instructor_curated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id <> canonical_id", name="ck_concepts_no_self_canonical"),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','merged')",
            name="ck_concepts_status_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_id"], ["concepts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["extracted_from_chunk_id"], ["chunks.id"], ondelete="SET NULL"),
    )
    # Replace placeholder embedding with pgvector type via raw DDL — pgvector
    # types aren't reliably emitted by Alembic ARRAY shorthand.
    op.execute("ALTER TABLE concepts DROP COLUMN embedding")
    op.execute("ALTER TABLE concepts ADD COLUMN embedding vector(3072)")
    op.create_index(
        "uq_concepts_course_lower_name",
        "concepts",
        ["course_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND canonical_id IS NULL"),
    )
    # HNSW index intentionally omitted — concepts table is small per-course; clustering is in-process (see services/concept_clustering.py).
    op.create_index(
        "idx_concepts_course",
        "concepts",
        ["course_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_concepts_course_status",
        "concepts",
        ["course_id", "status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ---------- concept_prerequisites ----------
    op.create_table(
        "concept_prerequisites",
        sa.Column("prereq_concept_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependent_concept_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strength", sa.Numeric(3, 2), nullable=False, server_default=sa.text("1.00")),
        sa.Column("instructor_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("prereq_concept_id", "dependent_concept_id"),
        sa.CheckConstraint(
            "prereq_concept_id <> dependent_concept_id",
            name="ck_concept_prerequisites_no_self",
        ),
        sa.CheckConstraint(
            "strength >= 0 AND strength <= 1",
            name="ck_concept_prerequisites_strength_range",
        ),
        sa.ForeignKeyConstraint(["prereq_concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dependent_concept_id"], ["concepts.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_concept_prerequisites_dependent",
        "concept_prerequisites",
        ["dependent_concept_id"],
    )

    # ---------- concept_tags ----------
    op.create_table(
        "concept_tags",
        sa.Column("concept_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_kind", sa.String(30), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weight", sa.Numeric(3, 2), nullable=False, server_default=sa.text("1.00")),
        sa.Column("role", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("concept_id", "target_kind", "target_id"),
        sa.CheckConstraint(
            "target_kind IN ('chunk','question','flashcard_card','pronunciation_item',"
            "'pool_item','objective','meeting','assignment')",
            name="ck_concept_tags_target_kind_valid",
        ),
        sa.CheckConstraint(
            "weight >= 0 AND weight <= 1",
            name="ck_concept_tags_weight_range",
        ),
        sa.CheckConstraint(
            "role IS NULL OR (target_kind = 'meeting' AND "
            "role IN ('introduced','covered','reinforced'))",
            name="ck_concept_tags_role_for_meeting",
        ),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_concept_tags_concept", "concept_tags", ["concept_id", "target_kind"])
    op.create_index(
        "idx_concept_tags_questions",
        "concept_tags",
        ["target_id"],
        postgresql_where=sa.text("target_kind = 'question'"),
    )
    op.create_index(
        "idx_concept_tags_chunks",
        "concept_tags",
        ["target_id"],
        postgresql_where=sa.text("target_kind = 'chunk'"),
    )
    op.create_index(
        "idx_concept_tags_pool_items",
        "concept_tags",
        ["target_id"],
        postgresql_where=sa.text("target_kind = 'pool_item'"),
    )
    op.create_index(
        "idx_concept_tags_meetings",
        "concept_tags",
        ["target_id"],
        postgresql_where=sa.text("target_kind = 'meeting'"),
    )
    op.create_index(
        "idx_concept_tags_assignments",
        "concept_tags",
        ["target_id"],
        postgresql_where=sa.text("target_kind = 'assignment'"),
    )

    # ---------- ALTER revision_attempts ----------
    op.add_column(
        "revision_attempts",
        sa.Column("primary_concept_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "revision_attempts_primary_concept_id_fkey",
        "revision_attempts",
        "concepts",
        ["primary_concept_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_revision_attempts_concept",
        "revision_attempts",
        ["user_id", "primary_concept_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("primary_concept_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_revision_attempts_concept", table_name="revision_attempts")
    op.drop_constraint(
        "revision_attempts_primary_concept_id_fkey",
        "revision_attempts",
        type_="foreignkey",
    )
    op.drop_column("revision_attempts", "primary_concept_id")

    op.drop_index("idx_concept_tags_assignments", table_name="concept_tags")
    op.drop_index("idx_concept_tags_meetings", table_name="concept_tags")
    op.drop_index("idx_concept_tags_pool_items", table_name="concept_tags")
    op.drop_index("idx_concept_tags_chunks", table_name="concept_tags")
    op.drop_index("idx_concept_tags_questions", table_name="concept_tags")
    op.drop_index("idx_concept_tags_concept", table_name="concept_tags")
    op.drop_table("concept_tags")

    op.drop_index("idx_concept_prerequisites_dependent", table_name="concept_prerequisites")
    op.drop_table("concept_prerequisites")

    op.drop_index("idx_concepts_course_status", table_name="concepts")
    op.drop_index("idx_concepts_course", table_name="concepts")
    op.drop_index("uq_concepts_course_lower_name", table_name="concepts")
    op.drop_table("concepts")
