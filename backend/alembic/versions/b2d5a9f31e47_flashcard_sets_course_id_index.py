"""flashcard_sets: index course_id

``flashcard_sets.course_id`` is NOT NULL and is the filter behind "list the
sets for this course", but it had no index, so every such listing seq-scans the
table. The sibling table ``pronunciation_sets`` already carries the equivalent
``ix_pronunciation_sets_course_id``; this one was simply missed.

Revision ID: b2d5a9f31e47
Revises: a1c4f8e2d905
Create Date: 2026-08-07
"""

from alembic import op


revision = "b2d5a9f31e47"
down_revision = "a1c4f8e2d905"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_flashcard_sets_course_id", "flashcard_sets", ["course_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_flashcard_sets_course_id", table_name="flashcard_sets")
