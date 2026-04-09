"""live quiz: LiveSession extensions + LiveAnswer table

Revision ID: 3f8a2b1c9d7e
Revises: 219a6239faac
Create Date: 2026-04-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f8a2b1c9d7e"
down_revision: Union[str, None] = "219a6239faac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Extend live_sessions with new columns --
    op.add_column(
        "live_sessions",
        sa.Column("join_code", sa.String(6), nullable=True),
    )
    op.create_unique_constraint(
        "uq_live_sessions_join_code", "live_sessions", ["join_code"]
    )
    op.add_column(
        "live_sessions",
        sa.Column("time_limit_seconds", sa.Integer(), server_default="30"),
    )
    op.add_column(
        "live_sessions",
        sa.Column("settings", JSONB(), server_default="{}"),
    )

    # -- Create live_answers table --
    op.create_table(
        "live_answers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("live_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("answer", sa.String(10), nullable=False),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("points_earned", sa.Integer(), server_default="0"),
        sa.UniqueConstraint(
            "session_id",
            "user_id",
            "question_index",
            name="uq_live_answers_session_user_question",
        ),
    )


def downgrade() -> None:
    op.drop_table("live_answers")
    op.drop_constraint(
        "uq_live_sessions_join_code", "live_sessions", type_="unique"
    )
    op.drop_column("live_sessions", "settings")
    op.drop_column("live_sessions", "time_limit_seconds")
    op.drop_column("live_sessions", "join_code")
