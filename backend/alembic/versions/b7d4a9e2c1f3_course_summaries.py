"""course_summaries table for persisted AI course summaries

Revision ID: b7d4a9e2c1f3
Revises: 8231060f9c65
Create Date: 2026-04-13 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b7d4a9e2c1f3"
down_revision: Union[str, None] = "8231060f9c65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "course_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_text", sa.String(), nullable=False),
        sa.Column("document_ids", postgresql.JSONB(), nullable=True),
        sa.Column(
            "generated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("course_id", name="uq_course_summaries_course_id"),
    )


def downgrade() -> None:
    op.drop_table("course_summaries")
