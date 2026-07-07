"""work_item_progress table + RLS

Revision ID: e6c2b8f4a19d
Revises: d5b1a7c93e6f
Create Date: 2026-07-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e6c2b8f4a19d'
down_revision: Union[str, None] = 'd5b1a7c93e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # work_item_progress — the student-owned per-item state row table (P4 Task
    # B2, spec §4.6; Decision 2). Owner is user_id; per-student checklist state
    # lives here while the operational spine (work_items) stays no-RLS. status
    # ships the FULL §4.6 lifecycle now so no later widening. One row per
    # (work_item_id, user_id) — a state transition upserts in place (Decision 3).
    op.create_table(
        "work_item_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "work_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','submitted','late',"
            "'missed','completed','follow_up_assigned')",
            name="ck_work_item_progress_status_valid",
        ),
        sa.UniqueConstraint(
            "work_item_id", "user_id", name="uq_work_item_progress_item_user"
        ),
    )
    # user_id lookup index for owner-scoped reads. (The unique constraint above
    # already indexes the (work_item_id, user_id) prefix, covering item lookups.)
    op.create_index(
        "ix_work_item_progress_user_id", "work_item_progress", ["user_id"]
    )

    # RLS — student-owned table (Decision 2; pattern 28236be3d7b3). Owner is
    # user_id; enforcement runs under non-superuser meli_app (postgres has
    # BYPASSRLS, set in 28236be3d7b3). The app.current_user_id GUC is set per
    # request by deps.py::get_current_user via set_config(...).
    op.execute("ALTER TABLE work_item_progress ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS work_item_progress_owner_isolation ON work_item_progress"
    )
    op.execute(
        "CREATE POLICY work_item_progress_owner_isolation ON work_item_progress "
        "FOR ALL "
        "USING (user_id = current_setting('app.current_user_id', true)::uuid) "
        "WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS work_item_progress_owner_isolation ON work_item_progress"
    )
    op.execute("ALTER TABLE work_item_progress DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_work_item_progress_user_id", table_name="work_item_progress"
    )
    op.drop_table("work_item_progress")
