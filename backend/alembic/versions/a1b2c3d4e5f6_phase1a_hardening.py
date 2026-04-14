"""phase1a hardening: role/status check constraints and rate-limit index fix

Revision ID: a1b2c3d4e5f6
Revises: 2444c2e5c265
Create Date: 2026-04-13 12:40:00.000000

Adds DB-level enforcement for role/status values and corrects the
api_usage rate-limit composite index to match the actual query pattern
(filter on user_id + created_at only, not endpoint).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "2444c2e5c265"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_users_role_valid",
        "users",
        "role IN ('student', 'instructor')",
    )
    op.create_check_constraint(
        "ck_documents_status_valid",
        "documents",
        "status IN ('pending', 'processing', 'ready', 'failed')",
    )

    # The rate-limit query filters by (user_id, created_at) without endpoint,
    # so the old composite index cannot be used effectively. Replace with an
    # index whose leading columns match the query.
    op.drop_index("idx_api_usage_rate_limit", table_name="api_usage")
    op.create_index(
        "idx_api_usage_rate_limit",
        "api_usage",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_api_usage_rate_limit", table_name="api_usage")
    op.create_index(
        "idx_api_usage_rate_limit",
        "api_usage",
        ["user_id", "endpoint", "created_at"],
    )

    op.drop_constraint("ck_documents_status_valid", "documents", type_="check")
    op.drop_constraint("ck_users_role_valid", "users", type_="check")
