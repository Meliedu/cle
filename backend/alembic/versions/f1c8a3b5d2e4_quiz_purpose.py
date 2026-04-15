"""add purpose column to quizzes

Revision ID: f1c8a3b5d2e4
Revises: e9a7c1f2b834
Create Date: 2026-04-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1c8a3b5d2e4"
down_revision: Union[str, None] = "e9a7c1f2b834"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quizzes",
        sa.Column(
            "purpose",
            sa.String(length=20),
            nullable=False,
            server_default="after_class",
        ),
    )
    op.create_check_constraint(
        "ck_quizzes_purpose_valid",
        "quizzes",
        "purpose IN ('after_class', 'live')",
    )
    op.create_index(
        "ix_quizzes_course_id_purpose",
        "quizzes",
        ["course_id", "purpose"],
    )


def downgrade() -> None:
    op.drop_index("ix_quizzes_course_id_purpose", table_name="quizzes")
    op.drop_constraint("ck_quizzes_purpose_valid", "quizzes", type_="check")
    op.drop_column("quizzes", "purpose")
