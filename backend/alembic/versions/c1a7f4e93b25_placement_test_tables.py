"""placement test tables (Meli Placement Test v1.2)

Eight tables for the pre-enrolment placement assessment.

Two structural choices are worth stating here because they are security
requirements, not preferences:

* ``placement_items`` (delivery) and ``placement_item_keys`` (key, transcript,
  rationale, reference band) are separate tables. The spec requires item
  delivery to be storage-separate from key storage; with one table, a careless
  ``SELECT *`` on the student path leaks the answer key.
* ``placement_audit_events`` exists rather than reusing ``audit_events``,
  because that table's ``course_id`` is NOT NULL and placement happens before
  the learner has any course.

RLS follows the owner-isolation pattern established in ``28236be3d7b3`` and
reused by ``readiness_responses``/``reports``/``checkpoint_responses``:
student-owned rows carry a policy on ``app.current_user_id``, and reviewer
access is authorised at the application layer. ``placement_responses`` carries
its own ``user_id`` because a row policy cannot follow a foreign key.

Revision ID: c1a7f4e93b25
Revises: b8d2f5c31a90
Create Date: 2026-07-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c1a7f4e93b25"
down_revision: Union[str, None] = "b8d2f5c31a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ATTEMPT_STATES = (
    "created", "eligibility_confirmed", "instructions_acknowledged", "in_progress",
    "submitted", "scored", "review_pending", "approved", "overridden",
    "advising_required", "released",
    "expired", "invalidated", "abandoned", "technical_review",
)
VERSION_STATUSES = ("draft", "candidate", "published", "retired")
FORM_STATUSES = ("active", "disabled", "compromised")
SECTIONS = ("listening", "language_use", "reading")
REVIEW_ACTIONS = ("approve", "override", "request_advising", "invalidate", "release")

#: Student-owned tables: (table, owner column).
RLS_TABLES = (
    ("placement_attempts", "user_id"),
    ("placement_responses", "user_id"),
)


def _values(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "placement_test_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version_code", sa.String(length=80), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("blueprint_hash", sa.String(length=64), nullable=False),
        sa.Column("scoring_rule_version", sa.String(length=40), nullable=False),
        sa.Column("key_version", sa.String(length=40), nullable=False),
        sa.Column("review_policy_version", sa.String(length=40), nullable=False),
        sa.Column("privacy_policy_version", sa.String(length=40), nullable=False),
        sa.Column("source_package", sa.String(length=120)),
        sa.Column("window_opens_at", sa.DateTime(timezone=True)),
        sa.Column("window_closes_at", sa.DateTime(timezone=True)),
        sa.Column(
            "max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")
        ),
        sa.Column(
            "duration_minutes", sa.Integer(), nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "claim_boundary", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "review_policy", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "published_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("version_code", name="uq_placement_versions_code"),
        sa.CheckConstraint(
            f"status IN ({_values(VERSION_STATUSES)})",
            name="ck_placement_versions_status_valid",
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 5", name="ck_placement_versions_max_attempts"
        ),
        sa.CheckConstraint(
            "window_closes_at IS NULL OR window_opens_at IS NULL "
            "OR window_closes_at > window_opens_at",
            name="ck_placement_versions_window_order",
        ),
    )
    # At most one published version: two would make "which rules scored this
    # attempt" ambiguous for work already in flight.
    op.create_index(
        "uq_placement_versions_single_published",
        "placement_test_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )

    op.create_table(
        "placement_forms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_version_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("placement_test_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("form_code", sa.String(length=1), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("expected_seconds", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "linking_status", sa.String(length=30), nullable=False,
            server_default=sa.text("'not_established'"),
        ),
        sa.Column(
            "equating_status", sa.String(length=30), nullable=False,
            server_default=sa.text("'not_established'"),
        ),
        sa.Column(
            "audio_manifest", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "test_version_id", "form_code", name="uq_placement_forms_version_code"
        ),
        sa.CheckConstraint(
            f"status IN ({_values(FORM_STATUSES)})",
            name="ck_placement_forms_status_valid",
        ),
        sa.CheckConstraint("form_code ~ '^[A-E]$'", name="ck_placement_forms_code_valid"),
    )

    op.create_table(
        "placement_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "form_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("placement_forms.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("question_number", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=20), nullable=False),
        sa.Column("response_format", sa.String(length=20), nullable=False),
        sa.Column(
            "option_letters", postgresql.ARRAY(sa.String(length=1)), nullable=False
        ),
        sa.Column("expected_seconds", sa.Integer(), nullable=False),
        sa.Column("audio_playback", sa.Integer()),
        sa.Column("passage", sa.Text()),
        sa.Column("stem", sa.Text()),
        sa.Column("prompt", sa.Text()),
        sa.Column(
            "options", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "form_id", "question_number", name="uq_placement_items_form_question"
        ),
        sa.CheckConstraint(
            "question_number BETWEEN 1 AND 30", name="ck_placement_items_question_range"
        ),
        sa.CheckConstraint(
            f"section IN ({_values(SECTIONS)})", name="ck_placement_items_section_valid"
        ),
        sa.CheckConstraint(
            "audio_playback IS NULL OR audio_playback BETWEEN 1 AND 3",
            name="ck_placement_items_playback_range",
        ),
        sa.CheckConstraint(
            "expected_seconds > 0", name="ck_placement_items_expected_seconds"
        ),
        sa.CheckConstraint(
            "array_length(option_letters, 1) BETWEEN 2 AND 6",
            name="ck_placement_items_option_count",
        ),
    )

    op.create_table(
        "placement_item_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "item_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("placement_items.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "test_version_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("placement_test_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_item_id", sa.String(length=40), nullable=False),
        sa.Column("slot", sa.String(length=20), nullable=False),
        sa.Column("legacy_band", sa.Integer(), nullable=False),
        sa.Column("skill", sa.String(length=30), nullable=False),
        sa.Column("item_type", sa.String(length=80)),
        sa.Column("topic", sa.String(length=120)),
        sa.Column("subskill", sa.Text()),
        sa.Column("correct_answer", sa.String(length=20), nullable=False),
        sa.Column("answer_text", sa.Text()),
        sa.Column("rationale", sa.Text()),
        sa.Column("transcript", sa.Text()),
        sa.Column("target_vocabulary", sa.Text()),
        sa.Column("target_grammar", sa.Text()),
        sa.Column("copyright_status", sa.Text()),
        sa.Column("qa_status", sa.Text()),
        sa.Column(
            "teacher_flags", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("item_id", name="uq_placement_item_keys_item"),
        sa.UniqueConstraint(
            "test_version_id", "external_item_id",
            name="uq_placement_item_keys_external_id",
        ),
        sa.CheckConstraint(
            "legacy_band BETWEEN 1 AND 6", name="ck_placement_item_keys_band_range"
        ),
    )
    op.create_index(
        "ix_placement_item_keys_version", "placement_item_keys", ["test_version_id"]
    )

    op.create_table(
        "placement_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "test_version_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("placement_test_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "form_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("placement_forms.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "state", sa.String(length=30), nullable=False,
            server_default=sa.text("'created'"),
        ),
        sa.Column(
            "allocation_reference", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("declared_band", sa.Integer()),
        sa.Column("accommodation", postgresql.JSONB()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("scored_at", sa.DateTime(timezone=True)),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column(
            "interruptions", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("raw_score", sa.Integer()),
        sa.Column("answered_count", sa.Integer()),
        sa.Column("band_scores", postgresql.JSONB()),
        sa.Column("skill_scores", postgresql.JSONB()),
        sa.Column("highest_sustained_band", sa.Integer()),
        sa.Column("provisional_course", sa.String(length=20)),
        sa.Column("lower_band_break", sa.Boolean()),
        sa.Column("clear_next_band_boundary", sa.Boolean()),
        sa.Column("confidence", sa.String(length=10)),
        sa.Column(
            "review_flags", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("scored_key_version", sa.String(length=40)),
        sa.Column("scored_rule_version", sa.String(length=40)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id", "test_version_id", "attempt_number",
            name="uq_placement_attempts_user_version_number",
        ),
        sa.CheckConstraint(
            f"state IN ({_values(ATTEMPT_STATES)})",
            name="ck_placement_attempts_state_valid",
        ),
        sa.CheckConstraint(
            "attempt_number BETWEEN 1 AND 5", name="ck_placement_attempts_number_range"
        ),
        sa.CheckConstraint(
            "raw_score IS NULL OR raw_score BETWEEN 0 AND 30",
            name="ck_placement_attempts_raw_score_range",
        ),
        sa.CheckConstraint(
            "highest_sustained_band IS NULL OR highest_sustained_band BETWEEN 0 AND 6",
            name="ck_placement_attempts_band_range",
        ),
        sa.CheckConstraint(
            "declared_band IS NULL OR declared_band BETWEEN 0 AND 6",
            name="ck_placement_attempts_declared_band_range",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('high','medium','review')",
            name="ck_placement_attempts_confidence_valid",
        ),
    )
    # One live attempt per learner per version: a double-tap on "Start" would
    # otherwise mint a second attempt and burn a form allocation.
    op.create_index(
        "uq_placement_attempts_single_open",
        "placement_attempts",
        ["user_id", "test_version_id"],
        unique=True,
        postgresql_where=sa.text(
            "state IN ('created','eligibility_confirmed',"
            "'instructions_acknowledged','in_progress')"
        ),
    )
    op.create_index("ix_placement_attempts_state", "placement_attempts", ["state"])
    op.execute(
        "CREATE INDEX ix_placement_attempts_review_queue "
        "ON placement_attempts (test_version_id, submitted_at DESC) "
        "WHERE state IN ('review_pending','technical_review')"
    )

    op.create_table(
        "placement_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attempt_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("placement_attempts.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "item_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("placement_items.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("question_number", sa.Integer(), nullable=False),
        sa.Column("response", sa.String(length=20)),
        sa.Column("is_correct", sa.Boolean()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column(
            "change_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "audio_play_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("time_spent_ms", sa.Integer()),
        sa.Column("connection_state", sa.String(length=20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "attempt_id", "item_id", name="uq_placement_responses_attempt_item"
        ),
        sa.CheckConstraint("change_count >= 0", name="ck_placement_responses_change_count"),
        sa.CheckConstraint(
            "audio_play_count >= 0", name="ck_placement_responses_audio_count"
        ),
    )
    op.create_index("ix_placement_responses_attempt", "placement_responses", ["attempt_id"])

    op.create_table(
        "placement_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attempt_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("placement_attempts.id", ondelete="CASCADE"), nullable=False,
        ),
        # No ondelete: the decision trail outlives the reviewer.
        sa.Column(
            "reviewer_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("system_recommendation", sa.String(length=20)),
        sa.Column("final_course", sa.String(length=20)),
        sa.Column("reason_code", sa.String(length=60)),
        sa.Column("reason_text", sa.Text()),
        sa.Column("evidence_snapshot_hash", sa.String(length=64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            f"action IN ({_values(REVIEW_ACTIONS)})",
            name="ck_placement_reviews_action_valid",
        ),
        sa.CheckConstraint(
            "action <> 'override' OR final_course IS NOT NULL",
            name="ck_placement_reviews_override_needs_course",
        ),
        sa.CheckConstraint(
            "action IN ('approve','release') OR reason_code IS NOT NULL",
            name="ck_placement_reviews_reason_required",
        ),
    )
    op.execute(
        "CREATE INDEX ix_placement_reviews_attempt "
        "ON placement_reviews (attempt_id, created_at DESC)"
    )

    op.create_table(
        "placement_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # No ondelete — the trail outlives the actor.
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")
        ),
        sa.Column("actor_role", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("entity_kind", sa.String(length=40), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before_hash", sa.String(length=64)),
        sa.Column("after_hash", sa.String(length=64)),
        sa.Column("request_id", sa.String(length=64)),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_placement_audit_entity",
        "placement_audit_events",
        ["entity_kind", "entity_id"],
    )
    op.execute(
        "CREATE INDEX ix_placement_audit_created "
        "ON placement_audit_events (created_at DESC)"
    )

    # RLS on the student-owned tables (pattern 28236be3d7b3). Enforcement runs
    # under the non-superuser meli_app role; postgres has BYPASSRLS.
    for table, owner_col in RLS_TABLES:
        policy = f"{table}_owner_isolation"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"CREATE POLICY {policy} ON {table} "
            f"FOR ALL "
            f"USING ({owner_col} = current_setting('app.current_user_id', true)::uuid) "
            f"WITH CHECK ({owner_col} = current_setting('app.current_user_id', true)::uuid)"
        )


def downgrade() -> None:
    for table, _owner_col in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("placement_audit_events")
    op.drop_table("placement_reviews")
    op.drop_table("placement_responses")
    op.drop_table("placement_attempts")
    op.drop_table("placement_item_keys")
    op.drop_table("placement_items")
    op.drop_table("placement_forms")
    op.drop_table("placement_test_versions")
