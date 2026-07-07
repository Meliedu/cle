"""activities + activity_responses tables + RLS

Revision ID: c7d2f4b9e6a1
Revises: b8e5d1a4c297
Create Date: 2026-07-08 15:00:00.000000

P5 Task B3 (spec §4.4/§4.5, Decision 3): ``activities`` is the course-scoped,
teacher-authored activity table — operational, mirrors ``checkpoints``/
``work_items``: **NO RLS** (endpoint-guarded). ``activity_responses`` is the
student-owned submission table — it COPIES the ``e6c2b8f4a19d``
(``work_item_progress``) owner-isolation structure verbatim: create table +
``ix_activity_responses_user_id`` + ENABLE ROW LEVEL SECURITY +
``activity_responses_owner_isolation`` policy keyed on the ``app.current_user_id``
GUC. **NO soft-delete** on the response row.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c7d2f4b9e6a1'
down_revision: Union[str, None] = 'b8e5d1a4c297'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # activities — course-scoped / teacher-authored activity (spec §4.4). Mirrors
    # checkpoints/work_items: NO RLS (endpoint-guarded). format ∈
    # swipe|vote|comment_reaction; status mirrors the checkpoint machine; the
    # §4.5 publish-settings ride on the row so a score-bearing activity carries
    # its own grade policy (Decision 3).
    op.create_table(
        "activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_meetings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "anonymous",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "score_category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("score_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("points", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("grading_mode", sa.String(length=20), nullable=True),
        sa.Column("late_rule", sa.String(length=20), nullable=True),
        sa.Column(
            "score_bearing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "format IN ('swipe','vote','comment_reaction')",
            name="ck_activities_format_valid",
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','live','closed','archived')",
            name="ck_activities_status_valid",
        ),
        sa.CheckConstraint(
            "grading_mode IS NULL OR grading_mode IN "
            "('auto','manual','participation')",
            name="ck_activities_grading_mode_valid",
        ),
        sa.CheckConstraint(
            "late_rule IS NULL OR late_rule IN "
            "('accept_late','reject_late','accept_with_flag')",
            name="ck_activities_late_rule_valid",
        ),
    )
    op.create_index("ix_activities_course_id", "activities", ["course_id"])

    # activity_responses — the student-owned per-activity submission row table
    # (Decision 3). COPIES the e6c2b8f4a19d (work_item_progress) owner-isolation
    # structure verbatim. One row per (activity_id, user_id) — a resubmit upserts
    # in place; comment_reaction stacks multiple reactions inside payload.
    op.create_table(
        "activity_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('on_time','late')",
            name="ck_activity_responses_status_valid",
        ),
        sa.UniqueConstraint(
            "activity_id", "user_id", name="uq_activity_responses_activity_user"
        ),
    )
    # user_id lookup index for owner-scoped reads. (The unique constraint above
    # already indexes the (activity_id, user_id) prefix, covering activity lookups.)
    op.create_index(
        "ix_activity_responses_user_id", "activity_responses", ["user_id"]
    )

    # RLS — student-owned table (Decision 3; pattern 28236be3d7b3 / e6c2b8f4a19d).
    # Owner is user_id; enforcement runs under non-superuser meli_app (postgres
    # has BYPASSRLS, set in 28236be3d7b3). The app.current_user_id GUC is set per
    # request by deps.py::get_current_user via set_config(...).
    op.execute("ALTER TABLE activity_responses ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS activity_responses_owner_isolation "
        "ON activity_responses"
    )
    op.execute(
        "CREATE POLICY activity_responses_owner_isolation ON activity_responses "
        "FOR ALL "
        "USING (user_id = current_setting('app.current_user_id', true)::uuid) "
        "WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS activity_responses_owner_isolation "
        "ON activity_responses"
    )
    op.execute("ALTER TABLE activity_responses DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_activity_responses_user_id", table_name="activity_responses"
    )
    op.drop_table("activity_responses")
    op.drop_index("ix_activities_course_id", table_name="activities")
    op.drop_table("activities")
