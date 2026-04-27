"""better_auth_id on users

Revision ID: b7e3d4f6a8c2
Revises: a1f9c3b7d5e2
Create Date: 2026-04-27

Adds users.better_auth_id (nullable, unique) so Better Auth user records can
link 1:1 with our existing local user UUIDs during the Clerk → Better Auth
migration. Once cutover is complete and every row is populated, a follow-up
migration will:
  - make the column NOT NULL
  - drop users.clerk_id

Until then, both columns coexist and `get_current_user` resolves the row by
whichever one is present in the verified JWT (dual-acceptance window).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e3d4f6a8c2"
down_revision: Union[str, None] = "a1f9c3b7d5e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("better_auth_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_users_better_auth_id",
        "users",
        ["better_auth_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_better_auth_id", table_name="users")
    op.drop_column("users", "better_auth_id")
