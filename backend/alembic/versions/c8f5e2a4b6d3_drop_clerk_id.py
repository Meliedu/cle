"""drop users.clerk_id

Revision ID: c8f5e2a4b6d3
Revises: b7e3d4f6a8c2
Create Date: 2026-04-27

Final step of the Clerk → Better Auth migration. Every public.users row
must already carry better_auth_id (verified via the migrate_clerk_to_better_auth
script run --live). Drops the legacy clerk_id column and makes
better_auth_id NOT NULL going forward.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f5e2a4b6d3"
down_revision: Union[str, None] = "b7e3d4f6a8c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Defensive guard: refuse to drop clerk_id if any row is still unlinked.
    # The migration script must run --live before this Alembic step.
    bind = op.get_bind()
    unlinked = bind.execute(
        sa.text("SELECT count(*) FROM users WHERE better_auth_id IS NULL")
    ).scalar_one()
    if unlinked:
        raise RuntimeError(
            f"Refusing to drop clerk_id: {unlinked} users still have "
            "better_auth_id NULL. Run migrate_clerk_to_better_auth --live first."
        )

    op.alter_column(
        "users", "better_auth_id", existing_type=sa.String(255), nullable=False
    )
    op.drop_column("users", "clerk_id")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("clerk_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_users_clerk_id_unique", "users", ["clerk_id"], unique=True)
    op.alter_column(
        "users", "better_auth_id", existing_type=sa.String(255), nullable=True
    )
