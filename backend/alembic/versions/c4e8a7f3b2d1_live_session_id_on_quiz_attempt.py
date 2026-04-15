"""Add live_session_id to quiz_attempts for dedup.

Adds a nullable live_session_id FK to quiz_attempts plus a partial unique
index on (user_id, live_session_id) so the end-of-session persist path
cannot insert duplicate attempts when fired more than once.

Revision ID: c4e8a7f3b2d1
Revises: b3f94e2a1c07
Create Date: 2026-04-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a7f3b2d1"
down_revision: Union[str, None] = "b3f94e2a1c07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quiz_attempts",
        sa.Column(
            "live_session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("live_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Partial unique: only enforce on rows that actually came from a live
    # session. Regular (after-class) attempts remain unconstrained.
    op.create_index(
        "uq_quiz_attempts_user_live_session",
        "quiz_attempts",
        ["user_id", "live_session_id"],
        unique=True,
        postgresql_where=sa.text("live_session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_quiz_attempts_user_live_session", table_name="quiz_attempts"
    )
    op.drop_column("quiz_attempts", "live_session_id")
