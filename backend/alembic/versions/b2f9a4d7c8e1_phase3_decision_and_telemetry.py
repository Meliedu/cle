"""phase 3 decision layer + outcome telemetry

Revision ID: b2f9a4d7c8e1
Revises: b2e9c4f7a1d3
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2f9a4d7c8e1"
down_revision: Union[str, None] = "b2e9c4f7a1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- ALTER courses: adaptive_engine_mode ----------
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
    # NOTE: ``expires_at > now()`` cannot appear in the index predicate —
    # ``now()`` is STABLE, and Postgres requires index predicates to be
    # IMMUTABLE. The reader filters expired rows at query time
    # (see ``get_or_recompute_next_actions``); this index just trims out
    # consumed rows from the partial.
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

    # ---------- instructor_alerts ----------
    op.create_table(
        "instructor_alerts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("reason", postgresql.JSONB, nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="ck_instructor_alerts_severity_valid",
        ),
        sa.CheckConstraint(
            "status IN ('open','dismissed','resolved')",
            name="ck_instructor_alerts_status_valid",
        ),
        sa.CheckConstraint(
            "alert_type IN ("
            "'student_disengaging','student_falling_behind',"
            "'cohort_concept_weakness','prereq_gap_for_upcoming_meeting',"
            "'low_quiz_participation','missed_deadline','content_gap'"
            ")",
            name="ck_instructor_alerts_alert_type_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["instructor_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["users.id"], ondelete="CASCADE",
        ),
        # Audit reference — no ondelete; user deletion is blocked while
        # rows reference them. Matches the project-wide audit FK pattern
        # (e.g. courses.instructor_id, documents.uploaded_by).
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
    )
    op.create_index(
        "idx_instructor_alerts_open",
        "instructor_alerts",
        ["instructor_id", "severity", sa.text("created_at DESC")],
        postgresql_where=sa.text("status = 'open'"),
    )
    # Idempotency support: at-most-one OPEN alert per (course, type, target).
    # NULL target_user_id is allowed (cohort-level alerts) and Postgres treats
    # NULLs as distinct in unique indexes — that's the behaviour we want, so we
    # don't add NULLS NOT DISTINCT here. Cohort alerts are deduped explicitly
    # by ``app.services.alerts._try_insert``: when target_user_id is None it
    # SELECTs for any open row matching (course_id, alert_type, NULL) and
    # skips the insert if one exists. Without that guard cohort alerts would
    # accumulate without DB enforcement.
    op.create_index(
        "uq_instructor_alerts_open_idempotent",
        "instructor_alerts",
        ["course_id", "alert_type", "target_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
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
        # Audit reference — see resolved_by note on instructor_alerts.
        sa.ForeignKeyConstraint(["set_by"], ["users.id"]),
    )
    op.create_index(
        "idx_engine_overrides_course",
        "engine_overrides",
        ["course_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_engine_overrides_course", table_name="engine_overrides")
    op.drop_table("engine_overrides")

    op.drop_index(
        "uq_instructor_alerts_open_idempotent", table_name="instructor_alerts"
    )
    op.drop_index("idx_instructor_alerts_open", table_name="instructor_alerts")
    op.drop_table("instructor_alerts")

    op.drop_index("idx_action_outcomes_course_action", table_name="action_outcomes")
    op.drop_index("idx_action_outcomes_user", table_name="action_outcomes")
    op.drop_index("idx_action_outcomes_variant_served", table_name="action_outcomes")
    op.drop_table("action_outcomes")

    op.drop_index("idx_next_actions_user_course", table_name="next_actions")
    op.drop_index("idx_next_actions_cleanup", table_name="next_actions")
    op.drop_index("idx_next_actions_user_active", table_name="next_actions")
    op.drop_table("next_actions")

    op.drop_constraint(
        "ck_courses_engine_mode_valid", "courses", type_="check",
    )
    op.drop_column("courses", "adaptive_engine_mode")
