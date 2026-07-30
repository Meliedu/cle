"""Placement test model family (Meli Placement Test v1.2 integration spec).

Placement is deliberately its own family rather than an extension of the quiz
tables. Three properties make it different in kind:

1. **It is pre-enrolment.** An attempt exists before the learner belongs to any
   course, so nothing here is course-scoped. ``audit_events`` cannot be reused
   for the same reason: its ``course_id`` is NOT NULL.
2. **Authority is a workflow state, not a score.** "A scoring response is not
   the same as a released recommendation or a final course decision"
   (Administrator Pack §8). The state machine below is the mechanism that makes
   that true rather than aspirational.
3. **Keys must be storage-separate from delivery.** The spec requires "item
   delivery separate from key/script/rationale storage", so the safe surface
   (:class:`PlacementItem`) and the restricted surface
   (:class:`PlacementItemKey`) are two tables with a 1:1 FK. A query against
   the delivery table cannot leak a key even if someone writes ``SELECT *``.

RLS follows the established owner-isolation pattern (``28236be3d7b3``):
``placement_attempts`` and ``placement_responses`` are student-owned and carry
an ``app.current_user_id`` policy. Reviewer access is authorised at the
application layer exactly as it is for ``reports`` and ``checkpoint_responses``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Ordered happy path. Every transition is checked in
#: ``services/placement_state.py``; the CHECK below only constrains the value.
ATTEMPT_STATES: tuple[str, ...] = (
    "created",
    "eligibility_confirmed",
    "instructions_acknowledged",
    "in_progress",
    "submitted",
    "scored",
    "review_pending",
    "approved",
    "overridden",
    "advising_required",
    "released",
)

#: Off-path terminals. Reachable from several states; never auto-entered from a
#: student action except ``expired`` (window/timer) and ``abandoned`` (sweep).
ATTEMPT_EXCEPTION_STATES: tuple[str, ...] = (
    "expired",
    "invalidated",
    "abandoned",
    "technical_review",
)

ALL_ATTEMPT_STATES = ATTEMPT_STATES + ATTEMPT_EXCEPTION_STATES

VERSION_STATUSES = ("draft", "candidate", "published", "retired")
FORM_STATUSES = ("active", "disabled", "compromised")
SECTIONS = ("listening", "language_use", "reading")
REVIEW_ACTIONS = (
    "approve", "override", "request_advising", "invalidate", "release",
    # Returns a technical_review attempt to the normal queue once the fault
    # is understood. Without it, the only legal exit was invalidation.
    "resume_review",
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ",".join(f"'{value}'" for value in values)
    return f"{column} IN ({joined})"


class PlacementTestVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One immutable content+rule version of the placement test.

    Every scored attempt pins the version, key version and scoring-rule version
    it was scored under. Without that, a later content or threshold change
    silently rewrites the meaning of results already released to learners.
    """

    __tablename__ = "placement_test_versions"
    __table_args__ = (
        UniqueConstraint("version_code", name="uq_placement_versions_code"),
        CheckConstraint(
            _in_list("status", VERSION_STATUSES),
            name="ck_placement_versions_status_valid",
        ),
        CheckConstraint(
            "max_attempts BETWEEN 1 AND 5",
            name="ck_placement_versions_max_attempts",
        ),
        CheckConstraint(
            "window_closes_at IS NULL OR window_opens_at IS NULL "
            "OR window_closes_at > window_opens_at",
            name="ck_placement_versions_window_order",
        ),
        # Only one version may be live at a time: two published versions would
        # make "which rules scored this attempt" ambiguous for in-flight work.
        Index(
            "uq_placement_versions_single_published",
            "status",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
    )

    version_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default=text("'draft'")
    )
    #: Hash of the reconstructed blueprint (forms x items x sections x bands).
    blueprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scoring_rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    key_version: Mapped[str] = mapped_column(String(40), nullable=False)
    review_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    privacy_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_package: Mapped[str | None] = mapped_column(String(120))

    window_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default=text("30")
    )

    #: Learner-facing purpose/privacy copy, lifted verbatim from the booklet so
    #: the product cannot quietly widen the claim the assessment makes.
    claim_boundary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: Versioned review thresholds (spec: "thresholds must be versioned
    #: configuration with audit history").
    review_policy: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlacementForm(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One of the five blueprint-parallel forms (A-E) of a version.

    ``linking_status``/``equating_status`` are stored, not assumed. The package
    is explicit that the forms are design-comparable only, and the UI must never
    describe them as interchangeable while these read ``not_established``.
    """

    __tablename__ = "placement_forms"
    __table_args__ = (
        UniqueConstraint(
            "test_version_id", "form_code", name="uq_placement_forms_version_code"
        ),
        CheckConstraint(
            _in_list("status", FORM_STATUSES), name="ck_placement_forms_status_valid"
        ),
        CheckConstraint(
            "form_code ~ '^[A-E]$'", name="ck_placement_forms_code_valid"
        ),
    )

    test_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placement_test_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    form_code: Mapped[str] = mapped_column(String(1), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
    linking_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="not_established",
        server_default=text("'not_established'"),
    )
    equating_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="not_established",
        server_default=text("'not_established'"),
    )
    audio_manifest: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class PlacementItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The student-safe delivery surface of one question.

    **Nothing restricted may ever be added to this table.** The key, transcript,
    rationale and reference band live in :class:`PlacementItemKey`. That split is
    the storage-level guarantee behind "never ship restricted fields to the
    student client"; a serializer bug cannot defeat a column that is not here.

    ``legacy_band`` is the one apparent exception and it is not stored here: the
    band a question targets is a restricted label (student booklets carry no
    band labels), so it lives on the key row and joins in only for scoring.
    """

    __tablename__ = "placement_items"
    __table_args__ = (
        UniqueConstraint(
            "form_id", "question_number", name="uq_placement_items_form_question"
        ),
        CheckConstraint(
            "question_number BETWEEN 1 AND 30",
            name="ck_placement_items_question_range",
        ),
        CheckConstraint(
            _in_list("section", SECTIONS), name="ck_placement_items_section_valid"
        ),
        CheckConstraint(
            "audio_playback IS NULL OR audio_playback BETWEEN 1 AND 3",
            name="ck_placement_items_playback_range",
        ),
        CheckConstraint(
            "expected_seconds > 0", name="ck_placement_items_expected_seconds"
        ),
        CheckConstraint(
            "array_length(option_letters, 1) BETWEEN 2 AND 6",
            name="ck_placement_items_option_count",
        ),
    )

    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placement_forms.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(20), nullable=False)
    #: ``choice_3`` / ``choice_4`` / ``sequence``.
    response_format: Mapped[str] = mapped_column(String(20), nullable=False)
    option_letters: Mapped[list[str]] = mapped_column(ARRAY(String(1)), nullable=False)
    expected_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_playback: Mapped[int | None] = mapped_column(Integer)

    passage: Mapped[str | None] = mapped_column(Text)
    stem: Mapped[str | None] = mapped_column(Text)
    prompt: Mapped[str | None] = mapped_column(Text)
    #: ``[{"letter": "A", "text": "…"}, …]`` in presentation order.
    options: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class PlacementItemKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Restricted per-item data. Never reachable from a student-facing route.

    Separate table, separate query, separate schema type. Every read of this
    table in application code sits behind an instructor/CLE dependency.
    """

    __tablename__ = "placement_item_keys"
    __table_args__ = (
        UniqueConstraint("item_id", name="uq_placement_item_keys_item"),
        UniqueConstraint(
            "test_version_id", "external_item_id",
            name="uq_placement_item_keys_external_id",
        ),
        CheckConstraint(
            "legacy_band BETWEEN 1 AND 6", name="ck_placement_item_keys_band_range"
        ),
        Index("ix_placement_item_keys_version", "test_version_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placement_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Denormalised so key-integrity checks and the review queue can scope by
    #: version without a three-table join on every row.
    test_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placement_test_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: The package's own identifier, e.g. ``HSK5-B-13``.
    external_item_id: Mapped[str] = mapped_column(String(40), nullable=False)
    slot: Mapped[str] = mapped_column(String(20), nullable=False)
    legacy_band: Mapped[int] = mapped_column(Integer, nullable=False)
    skill: Mapped[str] = mapped_column(String(30), nullable=False)
    item_type: Mapped[str | None] = mapped_column(String(80))
    topic: Mapped[str | None] = mapped_column(String(120))
    subskill: Mapped[str | None] = mapped_column(Text)

    correct_answer: Mapped[str] = mapped_column(String(20), nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    target_vocabulary: Mapped[str | None] = mapped_column(Text)
    target_grammar: Mapped[str | None] = mapped_column(Text)
    copyright_status: Mapped[str | None] = mapped_column(Text)
    qa_status: Mapped[str | None] = mapped_column(Text)

    #: Unresolved content defects, e.g. a teacher reporting that an item has no
    #: single defensible key. A blocking flag stops the version publishing and
    #: excludes the item from scoring.
    teacher_flags: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class PlacementAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One learner sitting of one form. Student-owned; RLS applies.

    Scores are recorded but carry no authority on their own: only a
    ``released`` state with a matching :class:`PlacementReview` may be shown as
    a recommendation, and even then it is provisional.
    """

    __tablename__ = "placement_attempts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "test_version_id", "attempt_number",
            name="uq_placement_attempts_user_version_number",
        ),
        CheckConstraint(
            _in_list("state", ALL_ATTEMPT_STATES),
            name="ck_placement_attempts_state_valid",
        ),
        CheckConstraint(
            "attempt_number BETWEEN 1 AND 5",
            name="ck_placement_attempts_number_range",
        ),
        CheckConstraint(
            "raw_score IS NULL OR raw_score BETWEEN 0 AND 30",
            name="ck_placement_attempts_raw_score_range",
        ),
        CheckConstraint(
            "highest_sustained_band IS NULL "
            "OR highest_sustained_band BETWEEN 0 AND 6",
            name="ck_placement_attempts_band_range",
        ),
        CheckConstraint(
            "declared_band IS NULL OR declared_band BETWEEN 0 AND 6",
            name="ck_placement_attempts_declared_band_range",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence IN ('high','medium','review')",
            name="ck_placement_attempts_confidence_valid",
        ),
        # One live attempt per learner per version. Without this a double-tap on
        # "Start" mints two attempts and burns an allocation.
        Index(
            "uq_placement_attempts_single_open",
            "user_id",
            "test_version_id",
            unique=True,
            postgresql_where=text(
                "state IN ('created','eligibility_confirmed',"
                "'instructions_acknowledged','in_progress')"
            ),
        ),
        Index("ix_placement_attempts_state", "state"),
        Index(
            "ix_placement_attempts_review_queue",
            "test_version_id",
            text("submitted_at DESC"),
            postgresql_where=text("state IN ('review_pending','technical_review')"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    test_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placement_test_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placement_forms.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="created", server_default=text("'created'")
    )

    #: Auditable record of *why* this form was allocated (spec: form rotation
    #: needs "an auditable allocation reference").
    allocation_reference: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: The learner's self-declared band, used only for the mismatch trigger.
    declared_band: Mapped[int | None] = mapped_column(Integer)
    accommodation: Mapped[dict | None] = mapped_column(JSONB)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When the controlled timer must stop accepting answers.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    #: Reconnects, tab hides, audio failures. Feeds the technical trigger.
    interruptions: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    raw_score: Mapped[int | None] = mapped_column(Integer)
    answered_count: Mapped[int | None] = mapped_column(Integer)
    #: ``{"1": 5, "2": 4, …}`` — correct count out of five per legacy band.
    band_scores: Mapped[dict | None] = mapped_column(JSONB)
    #: ``{"listening": {"correct": 9, "total": 12}, …}``.
    skill_scores: Mapped[dict | None] = mapped_column(JSONB)
    highest_sustained_band: Mapped[int | None] = mapped_column(Integer)
    provisional_course: Mapped[str | None] = mapped_column(String(20))
    lower_band_break: Mapped[bool | None] = mapped_column(Boolean)
    clear_next_band_boundary: Mapped[bool | None] = mapped_column(Boolean)
    confidence: Mapped[str | None] = mapped_column(String(10))
    #: Machine-readable trigger codes; never free text shown to a learner.
    review_flags: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    #: Pinned at scoring time so a later rule/key change cannot rewrite history.
    scored_key_version: Mapped[str | None] = mapped_column(String(40))
    scored_rule_version: Mapped[str | None] = mapped_column(String(40))


class PlacementResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One answer within one attempt. Student-owned; RLS applies.

    ``is_correct`` is written only at scoring time. Storing it on save would
    hand the client a correctness oracle by timing, and the spec forbids
    exposing keys during delivery.
    """

    __tablename__ = "placement_responses"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "item_id", name="uq_placement_responses_attempt_item"
        ),
        CheckConstraint(
            "change_count >= 0", name="ck_placement_responses_change_count"
        ),
        CheckConstraint(
            "audio_play_count >= 0", name="ck_placement_responses_audio_count"
        ),
        Index("ix_placement_responses_attempt", "attempt_id"),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placement_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placement_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: Denormalised for ordering the review view without joining items.
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Raw learner input: one letter, or a full order such as ``C-A-B``.
    response: Mapped[str | None] = mapped_column(String(20))
    is_correct: Mapped[bool | None] = mapped_column(Boolean)

    #: Owner column for RLS. Duplicated from the attempt because a row-level
    #: policy cannot follow a foreign key.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    audio_play_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    time_spent_ms: Mapped[int | None] = mapped_column(Integer)
    connection_state: Mapped[str | None] = mapped_column(String(20))


class PlacementReview(UUIDPrimaryKeyMixin, Base):
    """A CLE decision on an attempt. Append-only.

    No ``updated_at`` and no delete path: an override that can be edited later
    is not an override, it is a draft. Corrections are new rows.
    """

    __tablename__ = "placement_reviews"
    __table_args__ = (
        CheckConstraint(
            _in_list("action", REVIEW_ACTIONS), name="ck_placement_reviews_action_valid"
        ),
        CheckConstraint(
            "action <> 'override' OR final_course IS NOT NULL",
            name="ck_placement_reviews_override_needs_course",
        ),
        CheckConstraint(
            "action IN ('approve','release') OR reason_code IS NOT NULL",
            name="ck_placement_reviews_reason_required",
        ),
        Index("ix_placement_reviews_attempt", "attempt_id", text("created_at DESC")),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placement_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # No ondelete: the decision trail outlives the reviewer (audit FK pattern).
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    #: What the system proposed, captured at decision time so a later rescoring
    #: cannot make a reviewer look like they agreed with something else.
    system_recommendation: Mapped[str | None] = mapped_column(String(20))
    final_course: Mapped[str | None] = mapped_column(String(20))
    reason_code: Mapped[str | None] = mapped_column(String(60))
    reason_text: Mapped[str | None] = mapped_column(Text)
    #: Hash of the exact evidence bundle shown to the reviewer.
    evidence_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PlacementAuditEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only placement audit log.

    Separate from ``audit_events`` because that table requires a ``course_id``
    and placement happens before a learner has a course.
    """

    __tablename__ = "placement_audit_events"
    __table_args__ = (
        Index("ix_placement_audit_entity", "entity_kind", "entity_id"),
        Index("ix_placement_audit_created", text("created_at DESC")),
    )

    # No ondelete — the trail outlives the actor.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
