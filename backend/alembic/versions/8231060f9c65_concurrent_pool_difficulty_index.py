"""concurrent pool difficulty index

Revision ID: 8231060f9c65
Revises: 3c7d5e9f0a11
Create Date: 2026-04-13 20:16:34.528393

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8231060f9c65'
down_revision: Union[str, None] = '3c7d5e9f0a11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX IF EXISTS idx_pool_effective_difficulty")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pool_effective_difficulty "
            "ON revision_pool_items (course_id, content_type, "
            "(COALESCE(recalibrated_difficulty, difficulty)))"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_pool_effective_difficulty")
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_pool_effective_difficulty "
            "ON revision_pool_items (course_id, content_type, "
            "(COALESCE(recalibrated_difficulty, difficulty)))"
        )
