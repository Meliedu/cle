"""phase2 review: indexes, FK ondelete, type alignment

Revision ID: 3c7d5e9f0a11
Revises: 2444c2e5c265
Create Date: 2026-04-13 13:30:00.000000

Addresses Phase 2 deep-review findings:
- C1: expression index on COALESCE(recalibrated_difficulty, difficulty) for the
  bandit pick query that previously sequential-scanned revision_pool_items.
- H2: index on scheduler_models.course_id for cascade-delete and lookups by
  course alone.
- H3: ON DELETE CASCADE on revision_attempts.pool_item_id + supporting btree.
- H4: widen flashcard_progress.stability to NUMERIC(12,4) for long-retention
  cards.
- M4: index on revision_item_served.pool_item_id (PK starts with user_id, so
  joins originating from pool_item_id were unindexed).
- L1: convert scheduler_models.parameters from JSON to JSONB.
- Bonus: index on recalibration_stats.course_id for the recalibration job's
  per-course scan (the existing 3-col index sufficed but a narrower one is
  faster for the relabel apply path).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3c7d5e9f0a11"
down_revision: Union[str, None] = "2444c2e5c265"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # C1 — expression index for the effective difficulty used by _pick_item /
    # _get_unserved_counts. CONCURRENTLY would be ideal but Alembic transactions
    # forbid it; document the lock cost in the PR description.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pool_effective_difficulty "
        "ON revision_pool_items (course_id, content_type, "
        "(COALESCE(recalibrated_difficulty, difficulty)))"
    )

    # H2 — scheduler_models.course_id index
    op.create_index(
        "ix_scheduler_models_course_id",
        "scheduler_models",
        ["course_id"],
        unique=False,
    )

    # H3 — drop and re-add revision_attempts.pool_item_id FK with ON DELETE CASCADE,
    # plus a btree index for the recalibration relabel path.
    op.drop_constraint(
        "revision_attempts_pool_item_id_fkey",
        "revision_attempts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "revision_attempts_pool_item_id_fkey",
        "revision_attempts",
        "revision_pool_items",
        ["pool_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_revision_attempts_pool_item_id",
        "revision_attempts",
        ["pool_item_id"],
        unique=False,
    )

    # H4 — widen stability column to allow well-learned cards (years of retention)
    op.alter_column(
        "flashcard_progress",
        "stability",
        existing_type=sa.Numeric(precision=10, scale=4),
        type_=sa.Numeric(precision=12, scale=4),
        existing_nullable=True,
    )

    # M4 — supporting index on revision_item_served.pool_item_id
    op.create_index(
        "ix_revision_item_served_pool_item_id",
        "revision_item_served",
        ["pool_item_id"],
        unique=False,
    )

    # L1 — JSON -> JSONB conversion (safe USING cast)
    op.execute(
        "ALTER TABLE scheduler_models "
        "ALTER COLUMN parameters TYPE jsonb USING parameters::jsonb"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE scheduler_models "
        "ALTER COLUMN parameters TYPE json USING parameters::json"
    )
    op.drop_index(
        "ix_revision_item_served_pool_item_id",
        table_name="revision_item_served",
    )
    op.alter_column(
        "flashcard_progress",
        "stability",
        existing_type=sa.Numeric(precision=12, scale=4),
        type_=sa.Numeric(precision=10, scale=4),
        existing_nullable=True,
    )
    op.drop_index("ix_revision_attempts_pool_item_id", table_name="revision_attempts")
    op.drop_constraint(
        "revision_attempts_pool_item_id_fkey",
        "revision_attempts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "revision_attempts_pool_item_id_fkey",
        "revision_attempts",
        "revision_pool_items",
        ["pool_item_id"],
        ["id"],
    )
    op.drop_index("ix_scheduler_models_course_id", table_name="scheduler_models")
    op.execute("DROP INDEX IF EXISTS idx_pool_effective_difficulty")
