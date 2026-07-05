"""evidence-01: drop the autonomous decision engine

Removes the next_actions / action_outcomes / engine_overrides tables and the
``courses.adaptive_engine_mode`` column. These belonged to the autonomous
student-facing recommendation + A/B engine, which the Meli reviewed-evidence
pivot retires ("AI drafts and suggests; instructors review meaning and
action"). ``instructor_alerts`` is intentionally kept — it is reframed into
the Review-Case surface by a later evidence migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1f0e0d10001"
down_revision: Union[str, None] = "f4b8d2e6c1a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # action_outcomes references next_actions → drop it first.
    op.drop_table("action_outcomes")
    op.drop_table("next_actions")
    op.drop_table("engine_overrides")
    op.drop_constraint("ck_courses_engine_mode_valid", "courses", type_="check")
    op.drop_column("courses", "adaptive_engine_mode")


def downgrade() -> None:
    # ---------- courses.adaptive_engine_mode ----------
    op.add_column(
        "courses",
        sa.Column(
            "adaptive_engine_mode",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'on'"),
        ),
    )
    op.create_check_constraint(
        "ck_courses_engine_mode_valid",
        "courses",
        "adaptive_engine_mode IN ('on','off','random_50')",
    )

    # ---------- next_actions ----------
    op.create_table(
        "next_actions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("target_kind", sa.String(40), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority_score", sa.Numeric(7, 3), nullable=False),
        sa.Column("candidate_source", sa.String(20), nullable=False),
        sa.Column("reason", postgresql.JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "engine_variant", sa.String(20), nullable=False,
            server_default=sa.text("'on'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "action_type IN ("
            "'review_concept','prep_meeting','complete_assignment',"
            "'do_quiz','practice_weakness','catch_up_reading',"
            "'flashcard_review','pronunciation_practice','watch_recording'"
            ")",
            name="ck_next_actions_action_type_valid",
        ),
        sa.CheckConstraint(
            "target_kind IS NULL OR target_kind IN ("
            "'concept','course_meeting','assignment','quiz',"
            "'flashcard_set','pronunciation_set','document','chunk'"
            ")",
            name="ck_next_actions_target_kind_valid",
        ),
        sa.CheckConstraint(
            "candidate_source IN ('outer_fringe','deadline','review','fallback')",
            name="ck_next_actions_candidate_source_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_next_actions_user_active",
        "next_actions",
        ["user_id", sa.text("priority_score DESC")],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )
    op.create_index(
        "idx_next_actions_cleanup",
        "next_actions",
        ["expires_at"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )
    op.create_index(
        "idx_next_actions_user_course",
        "next_actions",
        ["user_id", "course_id"],
    )

    # ---------- action_outcomes ----------
    op.create_table(
        "action_outcomes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("next_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("target_kind", sa.String(40), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("engine_variant", sa.String(20), nullable=False),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "clicked", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "completed", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("outcome_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("outcome_metric", sa.String(40), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "outcome_metric IS NULL OR outcome_metric IN "
            "('mastery_delta','quiz_score','recall','completion')",
            name="ck_action_outcomes_metric_valid",
        ),
        sa.ForeignKeyConstraint(
            ["next_action_id"], ["next_actions.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_action_outcomes_variant_served",
        "action_outcomes",
        ["engine_variant", "served_at"],
    )
    op.create_index(
        "idx_action_outcomes_user",
        "action_outcomes",
        ["user_id", sa.text("served_at DESC")],
    )
    op.create_index(
        "idx_action_outcomes_course_action",
        "action_outcomes",
        ["course_id", "action_type"],
    )
    op.create_index(
        "uq_action_outcomes_next_action_id",
        "action_outcomes",
        ["next_action_id"],
        unique=True,
        postgresql_where=sa.text("next_action_id IS NOT NULL"),
    )

    # ---------- engine_overrides ----------
    op.create_table(
        "engine_overrides",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("set_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "set_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("user_id", "course_id"),
        sa.CheckConstraint(
            "mode IN ('on','off')",
            name="ck_engine_overrides_mode_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["set_by"], ["users.id"]),
    )
    op.create_index(
        "idx_engine_overrides_course",
        "engine_overrides",
        ["course_id"],
    )
