"""placement: record how many items actually carried a defensible key

A disputed key is excluded from the numerator, so a learner's result can rest on
29 items rather than 30. Nothing on the reviewer's screen said so, which
undermines the one thing the review surface exists for.

Revision ID: f2c8d3b71e94
Revises: e4f7b1a09c62
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2c8d3b71e94"
down_revision: Union[str, None] = "e4f7b1a09c62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "placement_attempts", sa.Column("scorable_count", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("placement_attempts", "scorable_count")
