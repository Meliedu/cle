"""action_outcomes: unique partial index on next_action_id

Revision ID: d1e3f5a8c4b9
Revises: c5d8e2f7a91b
Create Date: 2026-05-10

Two concurrent ``GET /next-actions`` requests can both observe "no outcome
row exists" for the same ``next_action_id`` and both insert, double-counting
served/clicked/completed in A/B summaries. Guard with a partial unique
index so insert-on-conflict-do-nothing serializes the writes.

Partial: ``WHERE next_action_id IS NOT NULL`` because the off-arm sentinel
rows ``app.api.next_actions.list_next_actions`` writes have a NULL
``next_action_id`` and must remain unique only by their daily de-dupe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e3f5a8c4b9"
down_revision: Union[str, None] = "c5d8e2f7a91b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_action_outcomes_next_action_id",
        "action_outcomes",
        ["next_action_id"],
        unique=True,
        postgresql_where=sa.text("next_action_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_action_outcomes_next_action_id", table_name="action_outcomes"
    )
