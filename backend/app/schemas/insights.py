"""Response schemas for the pure-read insights surface (P6).

These reshape existing evidence rows; they carry NO new computed fields beyond
grouping. The learning profile groups the caller's ``concept_mastery`` rows.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.evidence import EventStage, NoteReviewStatus


class ConceptMasteryEntry(BaseModel):
    """One reshaped ``concept_mastery`` row (values read as-is, never recomputed)."""

    concept_id: uuid.UUID
    concept_name: str
    mastery_score: Decimal
    confidence: Decimal
    attempt_count: int
    last_attempt_at: datetime | None


class LearningProfileGroups(BaseModel):
    """Concepts bucketed by the mastery/confidence thresholds ``api/mastery.py`` uses."""

    strong: list[ConceptMasteryEntry]
    developing: list[ConceptMasteryEntry]
    weak: list[ConceptMasteryEntry]


class LearningProfileResponse(BaseModel):
    """The caller's learning profile for one course.

    ``has_evidence`` is the discriminator the frontend uses to choose between the
    profile view and the designed no-evidence state (Decision 6): it is ``False``
    when there is no confident evidence (zero rows, or every row still below the
    ``confidence >= 0.5`` gate). ``disclaimer`` is the pilot
    ``claim_limits['learning_profile']`` copy, returned verbatim.
    """

    course_id: uuid.UUID
    has_evidence: bool
    concept_count: int
    groups: LearningProfileGroups
    disclaimer: str


class IloMapEntry(BaseModel):
    """One ``learning_objective`` row on the caller's ILO strength map (B5).

    ``strength`` is the mean ``concept_mastery.mastery_score`` over the concepts
    tagged to this objective (``concept_tags`` ``target_kind='objective'``) that
    have a mastery row for the CALLER — read as-is, never recomputed. It is
    ``None`` (and ``has_evidence=False``) when no tagged concept has caller
    evidence: the frontend renders the designed no-evidence cell, NEVER a
    fabricated 0 (Decision 7). ``concept_count`` is the number of live tagged
    concepts; ``evidence_concept_count`` how many of those the caller has attempted.
    """

    objective_id: uuid.UUID
    statement: str
    bloom_level: str | None
    has_evidence: bool
    strength: float | None
    concept_count: int
    evidence_concept_count: int


class IloMapResponse(BaseModel):
    """The caller's ILO strength map for one course (one entry per objective)."""

    course_id: uuid.UUID
    has_evidence: bool
    objectives: list[IloMapEntry]


class CohortIloMapEntry(BaseModel):
    """One ``learning_objective`` row on the cohort ILO strength map (B5, teacher).

    ``avg_strength`` is the row-level mean ``mastery_score`` over every student's
    mastery on this objective's tagged concepts (mirrors ``cohort_mastery``'s
    ``func.avg``); ``None`` with ``has_evidence=False`` when no student has
    evidence — never a fabricated 0. ``weak_students`` reuses the
    ``cohort_mastery`` weak definition (mastery < 0.5 among confidence >= 0.5),
    counted as DISTINCT students weak on any tagged concept.
    """

    objective_id: uuid.UUID
    statement: str
    bloom_level: str | None
    has_evidence: bool
    avg_strength: float | None
    weak_students: int
    students_with_evidence: int
    concept_count: int


class CohortIloMapResponse(BaseModel):
    """The cohort ILO strength map for one owned course (one entry per objective)."""

    course_id: uuid.UUID
    has_evidence: bool
    objectives: list[CohortIloMapEntry]


class SkillMapEntry(BaseModel):
    """One pilot ``skill_taxonomy`` skill on the skill-pattern map (B6).

    HONEST by construction (Decision 5): no ``skill`` link exists anywhere in the
    schema — ``concept_tags.target_kind`` has ``objective``/``checkpoint_card``/…
    but NOT ``skill``, and no evidence row carries a skill dimension. So every
    entry renders the no-evidence state: ``has_evidence=False`` with
    ``strength`` and ``sample_size`` both ``None``. The endpoint NEVER fabricates
    a score. The fields are forward-compatible: when a future concept→skill
    mapping lands, ``strength``/``sample_size`` populate and ``has_evidence``
    flips — only where real evidence exists. ``skill`` is the taxonomy id;
    ``label`` is a human-readable rendering of it.
    """

    skill: str
    label: str
    has_evidence: bool
    strength: float | None
    sample_size: int | None


class SkillMapResponse(BaseModel):
    """The caller's skill-pattern map for one course (one entry per pilot skill).

    A config-driven grid of the pilot ``skill_taxonomy``. Today ``has_evidence``
    is always ``False`` (no schema link exists — Decision 5); the frontend (F4)
    renders it as the honest "we don't have skill-level evidence yet" state.
    """

    course_id: uuid.UUID
    has_evidence: bool
    skills: list[SkillMapEntry]


class SignalDetail(BaseModel):
    """One ``learning_note`` reshaped for the "signal detail" view (B7, pure read).

    Security-sensitive (Decision 8, Core §0.2): the AI-drafted content
    (``observed_signal`` / ``draft_interpretation`` / ``limitation_note`` /
    ``evidence_category`` / ``context_anchor``) is only populated once the note
    is instructor-``reviewed``. ``waiting_for_review`` is the discriminator the
    frontend uses to render the designed waiting-for-instructor-feedback state:
    it is ``True`` for a student viewing their own still-``draft``/``queued``
    note (content withheld). An instructor viewing an owned signal always sees
    the content, so ``waiting_for_review`` is ``False`` for them.

    Structural metadata (``id``/``course_id``/``user_id``/``review_status``/
    timestamps) is always present — it leaks no AI interpretation and lets the
    waiting state render its shell.
    """

    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID | None
    review_status: NoteReviewStatus
    waiting_for_review: bool
    created_at: datetime
    updated_at: datetime

    # AI-drafted content — None unless the note is instructor-reviewed (or the
    # viewer is the owning instructor).
    evidence_category: str | None = None
    observed_signal: str | None = None
    draft_interpretation: str | None = None
    limitation_note: str | None = None
    context_anchor: dict | None = None
    outcome_status: str | None = None
    source_event_ids: list = []


class CohortMasterySummary(BaseModel):
    """The cohort mastery summary on the teacher course-insights payload (B8).

    A pure reduction of the ``api/mastery.py::cohort_mastery`` per-concept shape:
    ``avg_mastery`` is the mean of each live concept's cohort ``avg(mastery_score)``
    over the concepts that have any evidence (``None`` when none do — never a
    fabricated 0); ``weak_student_signals`` sums the ``cohort_mastery`` weak count
    (mastery < 0.5 among confidence >= 0.5) across concepts. Recomputes nothing.
    """

    concept_count: int
    concepts_with_evidence: int
    avg_mastery: float | None
    weak_student_signals: int


class AlertSeverityCounts(BaseModel):
    """Open ``instructor_alerts`` counts by severity (B8).

    These EQUAL ``GET /courses/{id}/alerts?status=open`` counted by severity —
    the endpoint reads the same rows, it does not re-evaluate any alert.
    """

    info: int = 0
    warning: int = 0
    critical: int = 0
    total: int = 0


class ReviewQueueDepth(BaseModel):
    """How much sits in the teacher's review queue (B8).

    ``open_alerts`` = open ``instructor_alerts``; ``pending_notes`` =
    ``learning_notes`` still in ``review_status ∈ {draft, queued}`` (AI-drafted,
    not yet instructor-reviewed). Both are counts of existing rows.
    """

    open_alerts: int
    pending_notes: int
    total: int


class CourseInsightsResponse(BaseModel):
    """The teacher course-insights payload for one owned course (B8, pure read).

    A single reshape of existing rows: the cohort mastery summary, open-alert
    severity counts, and review-queue depth. ``has_evidence`` is the frontend
    discriminator for the designed no-evidence state (Decision 6): ``False`` when
    the course has no cohort mastery evidence, no open alerts, and no pending
    notes.
    """

    course_id: uuid.UUID
    has_evidence: bool
    cohort_mastery: CohortMasterySummary
    alerts: AlertSeverityCounts
    review_queue: ReviewQueueDepth


class EffectivenessActionGroup(BaseModel):
    """One follow-up ``action_type`` bucket on the effectiveness tracker (B8).

    ``by_status`` counts this action type's ``outcome_checks`` by status (all
    seven CHECK statuses present, zeroed where absent). Read-only reshape.
    """

    action_type: str
    total: int
    by_status: dict[str, int]


class EffectivenessResponse(BaseModel):
    """The teacher effectiveness tracker for one owned course (B8, pure read).

    The read side of the loop ``services/mastery.py::_close_follow_ups`` writes:
    ``outcome_checks`` for the course grouped by ``status`` and, via the
    ``OutcomeCheck → FollowUpAction`` join, by follow-up ``action_type``
    (Decision 9). No new persistence, no new job. ``has_evidence`` is ``False``
    when the course has no outcome checks yet (designed empty payload).
    """

    course_id: uuid.UUID
    has_evidence: bool
    total: int
    by_status: dict[str, int]
    by_action_type: list[EffectivenessActionGroup]


class EvidenceSource(BaseModel):
    """One ``learning_event`` reshaped for the "where did this come from" view (B7).

    Surfaces the raw source signal (``source_kind`` / ``source_id`` / ``stage`` /
    ``event_type`` / ``value`` / ``occurred_at``) plus the ``context_anchor`` that
    a REVIEWED note attached to it, if any. Pure read; the event id is never
    trusted — the caller re-derives ``course_id``/``user_id`` and re-guards
    (Decision 8). For a student, ``context_anchor`` is only exposed from a
    reviewed note (an unreviewed draft's anchor is withheld, Core §0.2).
    """

    event_id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID
    source_kind: str
    source_id: uuid.UUID | None
    stage: EventStage
    event_type: str
    value: dict
    occurred_at: datetime
    context_anchor: dict | None = None
