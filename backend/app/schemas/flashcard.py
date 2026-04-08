import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class FlashcardCardResponse(BaseModel):
    id: uuid.UUID
    card_index: int
    front: str
    back: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardSetResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    card_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardSetDetailResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    cards: list[FlashcardCardResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardProgressUpdate(BaseModel):
    card_id: uuid.UUID
    quality: int = Field(ge=0, le=5)


class FlashcardProgressResponse(BaseModel):
    card_id: uuid.UUID
    ease_factor: Decimal
    interval_days: int
    repetitions: int
    next_review: datetime | None
    last_reviewed: datetime | None

    model_config = {"from_attributes": True}
