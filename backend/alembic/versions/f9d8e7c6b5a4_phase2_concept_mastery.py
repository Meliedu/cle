"""phase 2 concept mastery + history

Revision ID: f9d8e7c6b5a4
Revises: a3b1c2d4e5f6
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f9d8e7c6b5a4"
down_revision: Union[str, None] = "a3b1c2d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "concept_mastery",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("concept_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alpha", sa.Numeric(8, 3), nullable=False, server_default=sa.text("1.000")),
        sa.Column("beta", sa.Numeric(8, 3), nullable=False, server_default=sa.text("1.000")),
        sa.Column(
            "mastery_score",
            sa.Numeric(4, 3),
            sa.Computed("alpha / (alpha + beta)", persisted=True),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default=sa.text("0.000")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_correct_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_decay_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_meeting_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("user_id", "concept_id"),
        sa.CheckConstraint("alpha > 0", name="ck_concept_mastery_alpha_pos"),
        sa.CheckConstraint("beta > 0", name="ck_concept_mastery_beta_pos"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_concept_mastery_confidence_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["last_seen_meeting_id"], ["course_meetings.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "idx_concept_mastery_user_course",
        "concept_mastery",
        ["user_id", "course_id"],
    )
    op.create_index(
        "idx_concept_mastery_weak",
        "concept_mastery",
        ["course_id", "concept_id", "mastery_score"],
        postgresql_where=sa.text("mastery_score < 0.5 AND confidence > 0.3"),
    )
    op.create_index(
        "idx_concept_mastery_decay_due",
        "concept_mastery",
        ["last_decay_at"],
    )

    # History — for replay debugging + decay audit. Single insert per write,
    # so we keep it append-only without an FK to the row (PK rotates if a row
    # gets deleted-and-recreated).
    op.create_table(
        "concept_mastery_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("concept_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alpha", sa.Numeric(8, 3), nullable=False),
        sa.Column("beta", sa.Numeric(8, 3), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("source_kind", sa.String(20), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.Numeric(4, 3), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "event_type IN ('attempt','decay','replay','reset')",
            name="ck_concept_mastery_history_event_type_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_concept_mastery_history_user_concept_time",
        "concept_mastery_history",
        ["user_id", "concept_id", sa.text("recorded_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_concept_mastery_history_user_concept_time",
        table_name="concept_mastery_history",
    )
    op.drop_table("concept_mastery_history")
    op.drop_index("idx_concept_mastery_decay_due", table_name="concept_mastery")
    op.drop_index("idx_concept_mastery_weak", table_name="concept_mastery")
    op.drop_index("idx_concept_mastery_user_course", table_name="concept_mastery")
    op.drop_table("concept_mastery")
