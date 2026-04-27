import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


CardDifficulty = Literal["easy", "medium", "hard"]


class FlashcardCardResponse(BaseModel):
    id: uuid.UUID
    card_index: int
    front: str
    back: str
    difficulty: str = "medium"
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardSetResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    is_published: bool
    folder_id: uuid.UUID | None = None
    card_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardFolderResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardFolderCreate(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None


class FlashcardFolderRename(BaseModel):
    name: str


class FlashcardFolderMove(BaseModel):
    parent_id: uuid.UUID | None = None


class FlashcardSetMove(BaseModel):
    folder_id: uuid.UUID | None = None


class FlashcardSetDetailResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    is_published: bool
    cards: list[FlashcardCardResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardCardCreate(BaseModel):
    front: str = Field(min_length=1, max_length=500)
    back: str = Field(min_length=1, max_length=2000)
    difficulty: CardDifficulty = "medium"


class FlashcardCardUpdate(BaseModel):
    front: str | None = Field(default=None, max_length=500)
    back: str | None = Field(default=None, max_length=2000)
    difficulty: CardDifficulty | None = None


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
