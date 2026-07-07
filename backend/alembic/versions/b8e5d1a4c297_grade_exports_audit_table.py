"""grade_exports append-only audit table

Revision ID: b8e5d1a4c297
Revises: f7a3c9e1b024
Create Date: 2026-07-08 13:00:00.000000

P5 Task B2 (Decision 7): ``grade_exports`` is an append-only audit log — every
``GET /courses/{id}/grade-export.csv`` appends exactly one row BEFORE streaming
the CSV. The endpoint is owner-guarded (``get_owned_course``) so the table is
course-scoped / teacher-owned — **NO RLS**. Being an immutable audit log it
carries **NO soft-delete**: UUID PK + a plain ``created_at`` only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b8e5d1a4c297'
down_revision: Union[str, None] = 'f7a3c9e1b024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "grade_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exported_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "format",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'csv'"),
        ),
        sa.Column("filters", sa.JSON(), nullable=True),
        sa.Column(
            "row_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    # No RLS — course-scoped / teacher-owned (owner-guarded endpoint). No
    # soft-delete — append-only audit log.


def downgrade() -> None:
    op.drop_table("grade_exports")
