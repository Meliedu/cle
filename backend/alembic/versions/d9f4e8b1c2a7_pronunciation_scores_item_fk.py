"""pronunciation_scores: add pronunciation_item_id FK for concept mastery wiring

Closes the Phase 2 seam where pronunciation attempts could not feed
``update_concept_mastery`` because the score row had no link back to the
``pronunciation_items`` row it was about. Free-form practice (no item) keeps
working — the column is nullable and ON DELETE SET NULL so deleting an item
does not lose the historical score.

Revision ID: d9f4e8b1c2a7
Revises: c8a5e3b9f4d1
Create Date: 2026-05-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d9f4e8b1c2a7"
down_revision: Union[str, None] = "c8a5e3b9f4d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pronunciation_scores",
        sa.Column(
            "pronunciation_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pronunciation_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_pronunciation_scores_user_item",
        "pronunciation_scores",
        ["user_id", "pronunciation_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pronunciation_scores_user_item",
        table_name="pronunciation_scores",
    )
    op.drop_column("pronunciation_scores", "pronunciation_item_id")
