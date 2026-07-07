"""readiness_responses table + RLS

Revision ID: d94257fc717c
Revises: fe73ccfab9f9
Create Date: 2026-07-07 08:39:23.591838

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd94257fc717c'
down_revision: Union[str, None] = 'fe73ccfab9f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # readiness_responses — first P2 student-owned table (Decision 2). The phase
    # CHECK accepts all four spec §4.7 values for forward-compat (Decision 4).
    op.create_table(
        "readiness_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phase", sa.String(length=30), nullable=False),
        sa.Column(
            "answers",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "result",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'in_progress'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "phase IN ('eligibility_survey','ready_check','diagnostic','recommendation')",
            name="ck_readiness_responses_phase_valid",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress','completed')",
            name="ck_readiness_responses_status_valid",
        ),
        sa.UniqueConstraint(
            "user_id", "course_id", "phase", name="uq_readiness_user_course_phase"
        ),
    )
    # course_id lookup index for teacher-side / course-scoped reads. (The unique
    # constraint above already indexes the (user_id, course_id, phase) prefix,
    # covering owner lookups.)
    op.create_index(
        "ix_readiness_responses_course_id", "readiness_responses", ["course_id"]
    )

    # RLS — first P2 student-owned table (Decision 2; pattern 28236be3d7b3).
    # Owner is user_id; enforcement runs under non-superuser meli_app (postgres
    # has BYPASSRLS, set in 28236be3d7b3). The app.current_user_id GUC is set per
    # request by deps.py::get_current_user via set_config(...).
    op.execute("ALTER TABLE readiness_responses ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS readiness_responses_owner_isolation ON readiness_responses"
    )
    op.execute(
        "CREATE POLICY readiness_responses_owner_isolation ON readiness_responses "
        "FOR ALL "
        "USING (user_id = current_setting('app.current_user_id', true)::uuid) "
        "WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS readiness_responses_owner_isolation ON readiness_responses"
    )
    op.execute("ALTER TABLE readiness_responses DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_readiness_responses_course_id", table_name="readiness_responses")
    op.drop_table("readiness_responses")
