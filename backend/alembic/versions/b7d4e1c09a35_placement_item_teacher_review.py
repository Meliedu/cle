"""placement: carry the v1.3 teacher re-review ledger alongside the key

The v1.3 source package added an "Item Review" sheet: per item, the candidate
status, the teacher's priority, a twelve-dimension rubric, the excerpt under
review and the question the teacher is being asked to answer. Without it the
CLE review screen can only say an item is flagged, not why it is in front of
anyone, so reviewers were being sent back to the workbook to find out.

It lives on ``placement_item_keys`` rather than ``placement_items``
deliberately: ``evidence_excerpt`` quotes item content and the rubric reveals
where an item is considered weak, so it belongs on the restricted side of the
delivery/key split and inherits that table's instructor-only exposure.

Nullable with no default: banks extracted before v1.3 carry no ledger, and a
missing ledger is a real state ("this version predates the sheet"), not a
gap to be filled with an empty object.

Revision ID: b7d4e1c09a35
Revises: a9e5c2f74d18
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b7d4e1c09a35"
down_revision: Union[str, None] = "a9e5c2f74d18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "placement_item_keys",
        sa.Column("teacher_review", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("placement_item_keys", "teacher_review")
