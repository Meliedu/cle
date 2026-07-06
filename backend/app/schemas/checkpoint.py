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
