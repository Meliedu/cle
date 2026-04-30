"""phase 3 concept_mastery covering index for outer-fringe CTE

Revision ID: c8a5e3b9f4d1
Revises: b2f9a4d7c8e1
Create Date: 2026-05-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c8a5e3b9f4d1"
down_revision: Union[str, None] = "b2f9a4d7c8e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the original (user_id, course_id) index.
    op.drop_index("idx_concept_mastery_user_course", table_name="concept_mastery")
    # Recreate as a covering index. The outer-fringe CTE in
    # backend/app/services/outer_fringe.py projects (concept_id, mastery_score,
    # confidence) for the user/course pair; INCLUDE-ing them lets Postgres
    # serve the CTE entirely from the index, eliminating heap visits.
    op.execute(
        "CREATE INDEX idx_concept_mastery_user_course "
        "ON concept_mastery (user_id, course_id) "
        "INCLUDE (concept_id, mastery_score, confidence)"
    )


def downgrade() -> None:
    op.drop_index("idx_concept_mastery_user_course", table_name="concept_mastery")
    op.create_index(
        "idx_concept_mastery_user_course",
        "concept_mastery",
        ["user_id", "course_id"],
    )
