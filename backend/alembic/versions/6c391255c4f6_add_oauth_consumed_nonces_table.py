"""add oauth_consumed_nonces table

Persist consumed OAuth state nonces in Postgres so replay protection works
across multiple worker processes. The in-memory dict previously used in
``canvas_oauth.py`` silently allowed replays when a different worker
served the callback than the one that issued the state JWT.

Revision ID: 6c391255c4f6
Revises: f2247f8be863
Create Date: 2026-04-16 21:49:19.686581

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c391255c4f6'
down_revision: Union[str, None] = 'f2247f8be863'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_consumed_nonces",
        sa.Column("nonce", sa.String(128), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_oauth_consumed_nonces_expires_at",
        "oauth_consumed_nonces",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oauth_consumed_nonces_expires_at",
        table_name="oauth_consumed_nonces",
    )
    op.drop_table("oauth_consumed_nonces")
