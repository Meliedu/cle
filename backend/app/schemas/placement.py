"""Placement request/response schemas.

The type system carries the security boundary. :class:`PlacementItemOut` has no
field that could hold a key, an answer text, a transcript or a reference band,
so a student-facing route cannot serialise one even by mistake. The restricted
surface lives in :class:`ReviewResponseOut`, which is only ever returned from an
instructor-gated route.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Student-facing
# ---------------------------------------------------------------------------


class PlacementOptionOut(BaseModel):
    letter: str
    text: str


class PlacementItemOut(BaseModel):
    """One question as delivered. Safe fields only, by construction."""

    id: str
    question_number: int
    section: Literal["listening", "language_use", "reading"]
    response_format: str
    option_letters: list[str]
    expected_seconds: int
    audio_playback: int | None = None
    passage: str | None = None
    stem: str | None = None
    prompt: str | None = None
    options: list[PlacementOptionOut]


class PlacementIntroOut(BaseModel):
    """Everything shown before the timer starts (spec student flow, step 1).

    A closed or unpublished test is a *state*, not a failure: this returns 200
    with ``available: false`` rather than an error status. Answering "is the
    placement test open for me" with a 5xx would log a console error on a page
    that is working correctly, and would tell monitoring the service is down
    when it is merely between windows.
    """

    available: bool
    #: Why it is unavailable. ``not_published`` | ``window_closed``.
    unavailable_reason: str | None = None

    # Everything below describes a published test and is absent when there is
    # none, which is why each field carries a default.
    version_code: str | None = None
    duration_minutes: int = 30
    section_counts: dict[str, int] = {}
    total_items: int = 0
    max_attempts: int = 0
    attempts_used: int = 0
    attempts_remaining: int = 0
    purpose: str = ""
    privacy: str = ""
    window_opens_at: str | None = None
    window_closes_at: str | None = None
    #: Forms are blueprint-parallel, not equated. Surfaced so the UI can say so.
    comparability_note: str = ""


class AttemptStartIn(BaseModel):
    """What a learner may state about their own attempt.

    Deliberately does NOT accept an accommodation. Accommodation is an
    authority-bearing field: it extends the deadline and suppresses the
    long-duration review trigger. Accepting it from the learner's own request
    body let anyone grant themselves unlimited extra time and mute the one flag
    that would have caught it. It has to come from CLE.
    """

    #: The learner's own estimate, used only for the mismatch review trigger.
    #: Harmless to self-report: a wrong value only makes review MORE likely.
    declared_band: int | None = Field(default=None, ge=0, le=6)


class AttemptOut(BaseModel):
    id: str
    state: str
    attempt_number: int
    form_code: str
    #: False until CLE approves recorded audio for this form. While false the
    #: listening section is proctor-read, and the client must not offer a play
    #: control that would produce silence.
    audio_available: bool = False
    started_at: str | None = None
    expires_at: str | None = None
    submitted_at: str | None = None
    seconds_remaining: int | None = None
    answered_count: int = 0
    total_items: int = 0


class AttemptDetailOut(AttemptOut):
    items: list[PlacementItemOut] = []
    #: ``{item_id: response}`` so a reconnecting client restores its answers.
    saved_responses: dict[str, str | None] = {}


class ResponseSaveIn(BaseModel):
    item_id: str
    response: str | None = None
    time_spent_ms: int | None = Field(default=None, ge=0)
    audio_play_count: int | None = Field(default=None, ge=0)
    connection_state: str | None = None

    @field_validator("response")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ResponseSaveOut(BaseModel):
    item_id: str
    response: str | None
    change_count: int
    saved_at: str


class InterruptionIn(BaseModel):
    kind: str = Field(max_length=40)
    detail: str | None = Field(default=None, max_length=200)


class ResultOut(BaseModel):
    """What a learner may see.

    Deliberately thin. Before release there is a state and nothing else: no
    score, no band, no course. Releasing is what makes a recommendation exist,
    and a learner who could read the number early would be reading a decision
    CLE has not made.
    """

    attempt_id: str
    state: str
    released: bool
    submitted_at: str | None = None
    #: Present only once released.
    recommended_course: str | None = None
    #: The claim boundary travels with the result, always.
    claim_limit: str


# ---------------------------------------------------------------------------
# CLE / instructor-facing
# ---------------------------------------------------------------------------


class ReviewQueueItemOut(BaseModel):
    attempt_id: str
    student_name: str | None = None
    student_email: str | None = None
    attempt_number: int
    form_code: str
    state: str
    confidence: str | None = None
    provisional_course: str | None = None
    highest_sustained_band: int | None = None
    review_flags: list[str] = []
    submitted_at: str | None = None


class ReviewQueueOut(BaseModel):
    needs_review: int
    ready_to_approve: int
    blocked: int
    #: Across all pages, so a reviewer can tell there is more than this page.
    total: int = 0
    page: int = 1
    items: list[ReviewQueueItemOut]


class ReviewResponseOut(BaseModel):
    """Per-item evidence. Restricted: instructor routes only."""

    question_number: int
    section: str
    response_format: str
    legacy_band: int
    item_id: str
    correct_answer: str
    answer_text: str | None = None
    rationale: str | None = None
    teacher_flags: list[dict[str, Any]] = []
    response: str | None = None
    is_correct: bool | None = None
    change_count: int = 0
    time_spent_ms: int | None = None
    audio_play_count: int = 0


class PriorAttemptOut(BaseModel):
    attempt_id: str
    attempt_number: int
    state: str
    raw_score: int | None = None
    highest_sustained_band: int | None = None
    provisional_course: str | None = None
    confidence: str | None = None
    submitted_at: str | None = None


class ReviewDecisionOut(BaseModel):
    action: str
    system_recommendation: str | None = None
    final_course: str | None = None
    reason_code: str | None = None
    reason_text: str | None = None
    created_at: str | None = None


class AttemptEvidenceOut(BaseModel):
    attempt_id: str
    student_name: str | None = None
    student_email: str | None = None
    state: str
    form_code: str
    raw_score: int | None = None
    answered_count: int | None = None
    scorable_count: int | None = None
    band_scores: dict[str, int] | None = None
    skill_scores: dict[str, dict[str, int]] | None = None
    highest_sustained_band: int | None = None
    provisional_course: str | None = None
    lower_band_break: bool | None = None
    clear_next_band_boundary: bool | None = None
    confidence: str | None = None
    review_flags: list[str] = []
    duration_seconds: int | None = None
    declared_band: int | None = None
    interruptions: list[dict[str, Any]] = []
    key_version: str | None = None
    rule_version: str | None = None
    responses: list[ReviewResponseOut] = []
    prior_attempts: list[PriorAttemptOut] = []
    reviews: list[ReviewDecisionOut] = []
    #: Hash of exactly this bundle, echoed back on the decision so the record
    #: states what the reviewer was looking at.
    evidence_hash: str


COURSE_CODES = Literal[
    "LANG1511", "LANG1512", "LANG1513", "LANG1514", "LANG1515"
]


class DecisionIn(BaseModel):
    action: Literal[
        "approve", "override", "request_advising", "invalidate", "release",
        "resume_review",
    ]
    #: Constrained to the real course codes: this string is shown to the
    #: learner verbatim as their recommendation.
    final_course: COURSE_CODES | None = None
    reason_code: str | None = Field(default=None, max_length=60)
    reason_text: str | None = Field(default=None, max_length=2000)
    evidence_hash: str | None = None


class DecisionOut(BaseModel):
    attempt_id: str
    state: str
    action: str
    final_course: str | None = None


class PreflightFindingOut(BaseModel):
    code: str
    severity: str
    detail: str
    form_code: str | None = None
    question_number: int | None = None
    external_item_id: str | None = None


class PreflightOut(BaseModel):
    version_code: str
    status: str
    can_publish: bool
    blocking_count: int
    findings: list[PreflightFindingOut]


class VersionOut(BaseModel):
    id: str
    version_code: str
    status: str
    scoring_rule_version: str
    key_version: str
    max_attempts: int
    duration_minutes: int
    window_opens_at: str | None = None
    window_closes_at: str | None = None
    published_at: str | None = None
    form_count: int = 0
    item_count: int = 0
