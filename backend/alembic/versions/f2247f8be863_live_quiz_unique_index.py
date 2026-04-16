"""live_quiz_unique_index

Partial unique index on quizzes to close the TOCTOU race in
``POST /courses/{course_id}/quizzes/import-to-live``. The API layer keeps a
5-second select-then-insert fast-path to avoid hitting the DB on common
double-click traffic, but the authoritative guard is this index: any duplicate
that slips past the fast-path surfaces as an ``IntegrityError``, which the
endpoint catches and returns as HTTP 409.

Revision ID: f2247f8be863
Revises: c4e8a7f3b2d1
Create Date: 2026-04-16 13:15:28.679292

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2247f8be863'
down_revision: Union[str, None] = 'c4e8a7f3b2d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "uq_quizzes_live_title_per_course_creator"


def upgrade() -> None:
    # Partial unique index: one live-purpose quiz per (course, title, creator)
    # among rows not soft-deleted. Uses ``create_index`` with
    # ``postgresql_where`` so Alembic records it properly (op.execute would
    # work but would hide the index from autogenerate diffs).
    op.create_index(
        INDEX_NAME,
        "quizzes",
        ["course_id", "title", "created_by"],
        unique=True,
        postgresql_where=sa.text(
            "purpose = 'live' AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="quizzes")
