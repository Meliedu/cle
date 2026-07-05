"""concepts.cluster_id

Revision ID: a3b1c2d4e5f6
Revises: e7c4a9b1f2d8
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a3b1c2d4e5f6"
down_revision: Union[str, None] = "e7c4a9b1f2d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "concepts",
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "idx_concepts_cluster",
        "concepts",
        ["course_id", "cluster_id"],
        postgresql_where=sa.text("cluster_id IS NOT NULL AND status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("idx_concepts_cluster", table_name="concepts")
    op.drop_column("concepts", "cluster_id")
