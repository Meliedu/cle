"""Checkpoint / checkpoint-card schemas (Task 9).

DRAFT-only in P1 (Decision 3): these schemas cover teacher generation + card
CRUD. No publish/approve/schedule fields — those transitions ship in P3.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RemovedReason = Literal["not_needed", "duplicate", "not_covered", "other"]
CardKind = Literal["review_point", "final_comments"]
CloseRule = Literal["manual", "at_close_at", "end_of_session"]


class CheckpointGenerateRequest(BaseModel):
    """Trigger grounded checkpoint generation (T022). Without ``meeting_id`` the
    job drafts one checkpoint per non-deleted meeting in the course."""

    meeting_id: uuid.UUID | None = None
    review_card_count: int | None = Field(default=None, ge=1, le=10)


class CheckpointCardResponse(BaseModel):
    id: uuid.UUID
    checkpoint_id: uuid.UUID
    position: int
    kind: CardKind
    prompt: str
    document_id: uuid.UUID | None
    chunk_id: uuid.UUID | None
    objective_id: uuid.UUID | None
    removed: bool
    removed_reason: RemovedReason | None
    removed_note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CheckpointResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    meeting_id: uuid.UUID | None
    kind: str
    status: str
    title: str
    qr_enabled: bool
    release_at: datetime | None = None
    close_at: datetime | None = None
    close_rule: CloseRule | None = None
    generation_meta: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CheckpointWithCardsResponse(CheckpointResponse):
    cards: list[CheckpointCardResponse] = Field(default_factory=list)


class CheckpointCardUpdate(BaseModel):
    """Edit a card's prompt/source or soft-remove it with a reason. All fields
    optional (``exclude_unset`` applied server-side)."""

    prompt: str | None = Field(default=None, min_length=1, max_length=500)
    document_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None
    objective_id: uuid.UUID | None = None
    removed: bool | None = None
    removed_reason: RemovedReason | None = None
    removed_note: str | None = None


class CheckpointCardCreate(BaseModel):
    """Add a review-point card to a draft checkpoint. ``kind`` is server-forced
    to ``review_point`` — the single ``final_comments`` card is fixed."""

    prompt: str = Field(min_length=1, max_length=500)
    position: int | None = Field(default=None, ge=0)
    document_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None
    objective_id: uuid.UUID | None = None


class CheckpointScheduleRequest(BaseModel):
    """Schedule an ``approved`` checkpoint for future release (P3 T5).

    Fields are optional at the schema layer so a caller who omits them gets the
    typed ``REVIEW_REQUIRED`` gate (§3.4) rather than a bare 422 — the endpoint
    falls back to any values already set on the checkpoint and refuses when
    ``release_at``/``close_rule`` are still missing.
    """

    release_at: datetime | None = None
    close_at: datetime | None = None
    close_rule: CloseRule | None = None


class CheckpointPublishRequest(BaseModel):
    """Optional overrides applied before the publish gate (P3 T5).

    A direct publish from ``approved`` (immediate release) can supply the
    release timing here; a publish from ``scheduled`` typically sends no body
    and relies on the values persisted at schedule time.
    """

    release_at: datetime | None = None
    close_at: datetime | None = None
    close_rule: CloseRule | None = None


class CheckpointCardResult(BaseModel):
    """Per-card aggregate for the teacher results view (P3 T6, T048/T019).

    ``confidence_distribution`` is a histogram keyed ``"-2".."2"`` for
    ``review_point`` cards (every bucket present, zero-filled) and empty for
    ``final_comments`` cards, which instead surface ``text_response_count``.
    """

    card_id: uuid.UUID
    kind: CardKind
    prompt: str
    position: int
    response_count: int
    confidence_distribution: dict[str, int] = Field(default_factory=dict)
    text_response_count: int = 0


class StudentCheckpointCard(BaseModel):
    """A single card as the student sees it (no removal/audit fields, no
    answer key — cards carry only a prompt)."""

    id: uuid.UUID
    position: int
    kind: CardKind
    prompt: str

    model_config = {"from_attributes": True}


class CheckpointIntroResponse(BaseModel):
    """Student intro payload (P3 T7, S034) — the ordered live cards plus the
    minimal checkpoint context the mobile flow needs to render + submit."""

    checkpoint_id: uuid.UUID
    title: str
    status: str
    close_at: datetime | None = None
    cards: list[StudentCheckpointCard] = Field(default_factory=list)


class CheckpointResponseSubmit(BaseModel):
    """Submit one card's answer (P3 T7). ``confidence`` is the −2..+2 scale for
    ``review_point`` cards; ``text_response`` is the free-text answer for the
    ``final_comments`` card. Exactly one is supplied, enforced server-side
    against the card's ``kind``."""

    card_id: uuid.UUID
    confidence: int | None = Field(default=None, ge=-2, le=2)
    text_response: str | None = Field(default=None, max_length=2000)


class CheckpointResponseResult(BaseModel):
    """The persisted response row echoed back to the student."""

    id: uuid.UUID
    checkpoint_id: uuid.UUID
    card_id: uuid.UUID
    confidence: int | None
    text_response: str | None
    status: str
    submitted_at: datetime

    model_config = {"from_attributes": True}


class CheckpointResults(BaseModel):
    """Teacher results payload for a single checkpoint (P3 T6).

    ``missed_count`` is derived from the active-student roster (active-enrolled
    students with no response for this checkpoint) and is only meaningful once
    the checkpoint is ``closed``/``archived``.
    """

    checkpoint_id: uuid.UUID
    status: str
    active_student_count: int
    responded_count: int
    missed_count: int
    cards: list[CheckpointCardResult] = Field(default_factory=list)
