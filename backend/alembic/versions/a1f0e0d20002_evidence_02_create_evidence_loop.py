"""evidence-02: create the reviewed-evidence loop

Builds the Meli reviewed-evidence spine (Core OBJ-03..09, CLE §5.2):

* 6 new tables — learning_events, learning_notes, review_actions,
  follow_up_actions, outcome_checks, course_record_items.
* concept_tags — adds the Relationship Candidate review gate (CLE §5.4).
* instructor_alerts — adds Review Case linkage + broadens alert_type
  (reframed in-place; the table is NOT physically renamed).
* courses — adds the Course Context Package approval gate (CLE §6.5).

Governing rule (Core §0.2): AI drafts and suggests; instructors review.

Revision ID: a1f0e0d20002
Revises: a1f0e0d10001
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1f0e0d20002"
down_revision: Union[str, None] = "a1f0e0d10001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Original (narrow) instructor_alerts alert_type list, restored on downgrade.
_ALERT_TYPE_ORIGINAL = (
    "alert_type IN ("
    "'student_disengaging','student_falling_behind',"
    "'cohort_concept_weakness','prereq_gap_for_upcoming_meeting',"
    "'low_quiz_participation','missed_deadline','content_gap'"
    ")"
)
# Broadened list adding the Meli review-case types.
_ALERT_TYPE_BROADENED = (
    "alert_type IN ("
    "'student_disengaging','student_falling_behind',"
    "'cohort_concept_weakness','prereq_gap_for_upcoming_meeting',"
    "'low_quiz_participation','missed_deadline','content_gap',"
    "'readiness_gap','course_fit_concern','skill_gap'"
    ")"
)


def upgrade() -> None:
    # ---------- learning_events (OBJ-03) ----------
    op.create_table(
        "learning_events",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column(
            "value", postgresql.JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "visibility_scope", sa.String(20), nullable=False,
            server_default=sa.text("'instructor'"),
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "stage IN ('entry','before_class','during_class','after_class','review')",
            name="ck_learning_events_stage_valid",
        ),
        sa.CheckConstraint(
            "visibility_scope IN ('student','instructor','course_team')",
            name="ck_learning_events_visibility_scope_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_learning_events_course_user_time",
        "learning_events",
        ["course_id", "user_id", sa.text("occurred_at DESC")],
    )

    # ---------- learning_notes (OBJ-04) ----------
    op.create_table(
        "learning_notes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "source_event_ids", postgresql.JSONB, nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("context_anchor", postgresql.JSONB, nullable=True),
        sa.Column("evidence_category", sa.String(40), nullable=True),
        sa.Column("observed_signal", sa.Text(), nullable=False),
        sa.Column("draft_interpretation", sa.Text(), nullable=True),
        sa.Column("limitation_note", sa.Text(), nullable=True),
        sa.Column("suggested_follow_up", postgresql.JSONB, nullable=True),
        sa.Column(
            "review_status", sa.String(20), nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("outcome_status", sa.String(20), nullable=True),
        sa.Column(
            "report_eligibility", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "review_status IN ("
            "'draft','queued','reviewed','edited','merged','split','archived'"
            ")",
            name="ck_learning_notes_review_status_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_learning_notes_course_status",
        "learning_notes",
        ["course_id", "review_status"],
    )
    op.create_index(
        "idx_learning_notes_course_user",
        "learning_notes",
        ["course_id", "user_id"],
    )

    # ---------- review_actions (OBJ-06) ----------
    op.create_table(
        "review_actions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("learning_note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_role", sa.String(20), nullable=False),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("prior_status", sa.String(20), nullable=True),
        sa.Column("new_status", sa.String(20), nullable=True),
        sa.Column("edit_text", sa.Text(), nullable=True),
        sa.Column(
            "report_eligibility_change", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "action_type IN ("
            "'accept','edit','merge','split','assign_followup',"
            "'archive','carry_forward','mark_resolved'"
            ")",
            name="ck_review_actions_action_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["learning_note_id"], ["learning_notes.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_review_actions_note_time",
        "review_actions",
        ["learning_note_id", sa.text("created_at DESC")],
    )

    # ---------- follow_up_actions (OBJ-07) ----------
    op.create_table(
        "follow_up_actions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("learning_note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("target_kind", sa.String(40), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "assignment_status", sa.String(20), nullable=False,
            server_default=sa.text("'suggested'"),
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "assignment_status IN ("
            "'suggested','assigned','viewed','completed',"
            "'checked','closed','carried_forward'"
            ")",
            name="ck_follow_up_actions_assignment_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["learning_note_id"], ["learning_notes.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # Audit reference — no ondelete; matches project-wide audit FK pattern.
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"]),
    )
    op.create_index(
        "idx_follow_up_actions_user_course_status",
        "follow_up_actions",
        ["user_id", "course_id", "assignment_status"],
    )
    op.create_index(
        "idx_follow_up_actions_course_status",
        "follow_up_actions",
        ["course_id", "assignment_status"],
    )

    # ---------- outcome_checks (OBJ-08) ----------
    op.create_table(
        "outcome_checks",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learning_note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("follow_up_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ("
            "'pending','completed','improved','persistent',"
            "'resolved','needs_review','carried_forward'"
            ")",
            name="ck_outcome_checks_status_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["learning_note_id"], ["learning_notes.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["follow_up_action_id"], ["follow_up_actions.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_event_id"], ["learning_events.id"], ondelete="SET NULL",
        ),
    )
    # At-most-one closing outcome per follow-up (idempotency).
    op.create_index(
        "uq_outcome_checks_followup",
        "outcome_checks",
        ["follow_up_action_id"],
        unique=True,
        postgresql_where=sa.text("follow_up_action_id IS NOT NULL"),
    )
    op.create_index(
        "idx_outcome_checks_course_user",
        "outcome_checks",
        ["course_id", "user_id"],
    )

    # ---------- course_record_items (OBJ-09) ----------
    op.create_table(
        "course_record_items",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learning_note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("relationship_summary", postgresql.JSONB, nullable=True),
        sa.Column("action_summary", postgresql.JSONB, nullable=True),
        sa.Column("outcome_summary", postgresql.JSONB, nullable=True),
        sa.Column("instructor_comment", sa.Text(), nullable=True),
        sa.Column(
            "carry_forward", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "report_history", postgresql.JSONB, nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["learning_note_id"], ["learning_notes.id"], ondelete="SET NULL",
        ),
    )
    op.create_index(
        "idx_course_record_items_course_time",
        "course_record_items",
        ["course_id", sa.text("created_at DESC")],
    )

    # ---------- concept_tags: Relationship Candidate review gate (CLE §5.4) ----------
    op.add_column(
        "concept_tags",
        sa.Column("suggestion_source", sa.String(20), nullable=True),
    )
    op.add_column(
        "concept_tags",
        sa.Column("limitation", sa.String(), nullable=True),
    )
    op.add_column(
        "concept_tags",
        sa.Column(
            "review_status", sa.String(20), nullable=False,
            server_default=sa.text("'suggested'"),
        ),
    )
    op.add_column(
        "concept_tags",
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "concept_tags",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "concept_tags",
        sa.Column(
            "report_eligibility", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_foreign_key(
        "fk_concept_tags_reviewed_by_users",
        "concept_tags",
        "users",
        ["reviewed_by"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_concept_tags_review_status_valid",
        "concept_tags",
        "review_status IN ('suggested','reviewed','confirmed','edited','archived')",
    )
    op.create_check_constraint(
        "ck_concept_tags_suggestion_source_valid",
        "concept_tags",
        "suggestion_source IS NULL OR "
        "suggestion_source IN ('llm','inheritance','instructor')",
    )

    # ---------- instructor_alerts: Review Case linkage + broadened types ----------
    # Added AFTER learning_notes + follow_up_actions exist (FK targets).
    op.add_column(
        "instructor_alerts",
        sa.Column("linked_note_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "instructor_alerts",
        sa.Column("linked_follow_up_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "instructor_alerts",
        sa.Column(
            "report_eligibility", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_foreign_key(
        "fk_instructor_alerts_linked_note",
        "instructor_alerts",
        "learning_notes",
        ["linked_note_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_instructor_alerts_linked_follow_up",
        "instructor_alerts",
        "follow_up_actions",
        ["linked_follow_up_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "ck_instructor_alerts_alert_type_valid", "instructor_alerts", type_="check",
    )
    op.create_check_constraint(
        "ck_instructor_alerts_alert_type_valid",
        "instructor_alerts",
        _ALERT_TYPE_BROADENED,
    )

    # ---------- courses: Course Context Package approval gate (CLE §6.5) ----------
    op.add_column(
        "courses",
        sa.Column(
            "context_status", sa.String(20), nullable=False,
            server_default=sa.text("'draft'"),
        ),
    )
    op.add_column(
        "courses",
        sa.Column("context_approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_courses_context_status_valid",
        "courses",
        "context_status IN ('draft','approved')",
    )


def downgrade() -> None:
    # ---------- courses ----------
    op.drop_constraint(
        "ck_courses_context_status_valid", "courses", type_="check",
    )
    op.drop_column("courses", "context_approved_at")
    op.drop_column("courses", "context_status")

    # ---------- instructor_alerts ----------
    op.drop_constraint(
        "ck_instructor_alerts_alert_type_valid", "instructor_alerts", type_="check",
    )
    op.create_check_constraint(
        "ck_instructor_alerts_alert_type_valid",
        "instructor_alerts",
        _ALERT_TYPE_ORIGINAL,
    )
    op.drop_constraint(
        "fk_instructor_alerts_linked_follow_up", "instructor_alerts", type_="foreignkey",
    )
    op.drop_constraint(
        "fk_instructor_alerts_linked_note", "instructor_alerts", type_="foreignkey",
    )
    op.drop_column("instructor_alerts", "report_eligibility")
    op.drop_column("instructor_alerts", "linked_follow_up_id")
    op.drop_column("instructor_alerts", "linked_note_id")

    # ---------- concept_tags ----------
    op.drop_constraint(
        "ck_concept_tags_suggestion_source_valid", "concept_tags", type_="check",
    )
    op.drop_constraint(
        "ck_concept_tags_review_status_valid", "concept_tags", type_="check",
    )
    op.drop_constraint(
        "fk_concept_tags_reviewed_by_users", "concept_tags", type_="foreignkey",
    )
    op.drop_column("concept_tags", "report_eligibility")
    op.drop_column("concept_tags", "reviewed_at")
    op.drop_column("concept_tags", "reviewed_by")
    op.drop_column("concept_tags", "review_status")
    op.drop_column("concept_tags", "limitation")
    op.drop_column("concept_tags", "suggestion_source")

    # ---------- 6 tables (FK-safe reverse order) ----------
    op.drop_index(
        "idx_outcome_checks_course_user", table_name="outcome_checks",
    )
    op.drop_index("uq_outcome_checks_followup", table_name="outcome_checks")
    op.drop_table("outcome_checks")

    op.drop_index(
        "idx_course_record_items_course_time", table_name="course_record_items",
    )
    op.drop_table("course_record_items")

    op.drop_index("idx_review_actions_note_time", table_name="review_actions")
    op.drop_table("review_actions")

    op.drop_index(
        "idx_follow_up_actions_course_status", table_name="follow_up_actions",
    )
    op.drop_index(
        "idx_follow_up_actions_user_course_status", table_name="follow_up_actions",
    )
    op.drop_table("follow_up_actions")

    op.drop_index("idx_learning_notes_course_user", table_name="learning_notes")
    op.drop_index("idx_learning_notes_course_status", table_name="learning_notes")
    op.drop_table("learning_notes")

    op.drop_index(
        "idx_learning_events_course_user_time", table_name="learning_events",
    )
    op.drop_table("learning_events")
