"""phase 2 — defense-in-depth length checks on concept text columns

Revision ID: b2e9c4f7a1d3
Revises: f9d8e7c6b5a4
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b2e9c4f7a1d3"
down_revision: Union[str, None] = "f9d8e7c6b5a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_concepts_description_length",
        "concepts",
        "description IS NULL OR length(description) <= 2000",
    )
    op.create_check_constraint(
        "ck_concepts_name_length",
        "concepts",
        "length(name) <= 255",
    )


def downgrade() -> None:
    op.drop_constraint("ck_concepts_name_length", "concepts", type_="check")
    op.drop_constraint("ck_concepts_description_length", "concepts", type_="check")
