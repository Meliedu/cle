"""work_items table (course-scoped, no RLS)

Revision ID: d5b1a7c93e6f
Revises: c3a9f0e1d2b4
Create Date: 2026-07-08 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd5b1a7c93e6f'
down_revision: Union[str, None] = 'c3a9f0e1d2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # work_items — the course-scoped, teacher-authored checklist spine (P4 Task
    # B1, spec §4.6). Operational / teacher-owned — mirrors checkpoint_launches:
    # NO RLS (every read is enrollment- or owner-guarded at the endpoint layer).
    # Per-student state lives in the separate owner-owned work_item_progress
    # table (B2). source_kind ships the FULL §4.6 enum now (Decision 1) so no
    # later widening; P4 only WRITES 'checkpoint' + 'material'. The unique index
    # on (course_id, source_kind, source_id) makes the publish/backfill upsert
    # idempotent via on_conflict_do_nothing (Decision 3).
    op.create_table(
        "work_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "score_bearing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visible_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_kind IN ('checkpoint','practice','quiz','activity',"
            "'material','follow_up','report')",
            name="ck_work_items_source_kind_valid",
        ),
    )
    # Idempotency key for the publish/backfill upsert (Decision 3).
    op.create_index(
        "uq_work_items_course_source",
        "work_items",
        ["course_id", "source_kind", "source_id"],
        unique=True,
    )
    # No RLS — course-scoped / teacher-owned (Decision 2).


def downgrade() -> None:
    op.drop_index("uq_work_items_course_source", table_name="work_items")
    op.drop_table("work_items")
