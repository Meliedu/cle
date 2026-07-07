"""course_record_items decision/decided_by/decided_at

Revision ID: d5e8b3a6f214
Revises: c3f9a1d7b482
Create Date: 2026-07-08 18:00:00.000000

P7 Task B8 (spec §4.10, Decision 5): the course-memory decision triplet.
``course_record_items`` had NO decision column — this adds ``decision``
(CHECK ``keep|revise|reject|carry_forward``, nullable = undecided), ``decided_by``
(FK users, no ondelete — audit FK pattern, the decision trail outlives the
deciding user), and ``decided_at`` (tz). ``POST /memory/{id}/decide`` sets these
and syncs the existing ``carry_forward`` bool (true iff decision is
``carry_forward``). ``reject`` is an audited tombstone (the table has no
soft-delete), never a hard delete.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd5e8b3a6f214'
down_revision: Union[str, None] = 'c3f9a1d7b482'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_record_items",
        sa.Column("decision", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "course_record_items",
        sa.Column(
            "decided_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "course_record_items",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_course_record_items_decision_valid",
        "course_record_items",
        "decision IN ('keep','revise','reject','carry_forward')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_course_record_items_decision_valid",
        "course_record_items",
        type_="check",
    )
    op.drop_column("course_record_items", "decided_at")
    op.drop_column("course_record_items", "decided_by")
    op.drop_column("course_record_items", "decision")
