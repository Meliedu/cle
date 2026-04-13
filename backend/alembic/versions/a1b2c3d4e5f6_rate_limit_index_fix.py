"""rate-limit index matches query shape; chunk soft-delete column

Revision ID: a1b2c3d4e5f6
Revises: 2444c2e5c265
Create Date: 2026-04-13 00:00:00.000000

The original ``idx_api_usage_rate_limit`` indexed
``(user_id, endpoint, created_at)``. The rate-limit check filters on
``(user_id, created_at >= one_hour_ago)`` with no endpoint predicate, so the
endpoint column in the middle of the composite key prevents the range scan
on ``created_at`` from using the index efficiently. Replace it with
``(user_id, created_at)``.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "2444c2e5c265"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_api_usage_rate_limit")
    op.execute(
        "CREATE INDEX idx_api_usage_rate_limit "
        "ON api_usage (user_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_api_usage_rate_limit")
    op.execute(
        "CREATE INDEX idx_api_usage_rate_limit "
        "ON api_usage (user_id, endpoint, created_at)"
    )
