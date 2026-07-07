"""reports table + owner-isolation RLS (student-audience rows)

Revision ID: a1f3c8d5b2e7
Revises: c7d2f4b9e6a1
Create Date: 2026-07-08 16:00:00.000000

P7 Task B1 (spec §4.9, Decision 2): ``reports`` is the NEW course-scoped weekly /
end-term report table. ONE table serves both audiences (``audience`` ∈
``student|teacher``). A **student-audience** row carries ``user_id`` and is
owner-isolated via RLS — it COPIES the ``d94257fc717c`` (``readiness_responses``)
/ ``c7d2f4b9e6a1`` (``activity_responses``) owner-isolation structure verbatim:
``ix_reports_user_id`` + ENABLE ROW LEVEL SECURITY + ``reports_owner_isolation``
policy keyed on the ``app.current_user_id`` GUC. A **teacher course-level** row
has ``user_id = NULL`` — ``NULL = GUC`` is never true, so the policy never
matches it and students can never read it (teacher access is endpoint-guarded via
``get_owned_course``). **NO soft-delete** — a report archives via
``status='archived'``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1f3c8d5b2e7'
down_revision: Union[str, None] = 'c7d2f4b9e6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("audience", sa.String(length=20), nullable=False),
        # NULL = teacher course-level row (Decision 2). Owner of a student row.
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=True),
        sa.Column(
            "evidence_refs",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "export_history",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "audience IN ('student','teacher')",
            name="ck_reports_audience_valid",
        ),
        sa.CheckConstraint(
            "period IN ('weekly','end_term')",
            name="ck_reports_period_valid",
        ),
        sa.CheckConstraint(
            "status IN ('draft','reviewed','sent','archived')",
            name="ck_reports_status_valid",
        ),
    )
    # user_id lookup index for owner-scoped reads (COPY d94257fc717c pattern).
    op.create_index("ix_reports_user_id", "reports", ["user_id"])
    # Archive-list query support: teacher archive filters by these three.
    op.create_index(
        "ix_reports_course_audience_period",
        "reports",
        ["course_id", "audience", "period"],
    )

    # RLS — student-owned rows (Decision 2; pattern 28236be3d7b3 /
    # d94257fc717c). Owner is user_id; enforcement runs under non-superuser
    # meli_app (postgres has BYPASSRLS, set in 28236be3d7b3). The
    # app.current_user_id GUC is set per request by deps.py::get_current_user.
    # Teacher course-level rows (user_id = NULL) never satisfy the predicate, so
    # students can never read them.
    op.execute("ALTER TABLE reports ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS reports_owner_isolation ON reports"
    )
    op.execute(
        "CREATE POLICY reports_owner_isolation ON reports "
        "FOR ALL "
        "USING (user_id = current_setting('app.current_user_id', true)::uuid) "
        "WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS reports_owner_isolation ON reports")
    op.execute("ALTER TABLE reports DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_reports_course_audience_period", table_name="reports")
    op.drop_index("ix_reports_user_id", table_name="reports")
    op.drop_table("reports")
