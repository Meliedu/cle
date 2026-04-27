import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ItemType = Literal["word", "phrase", "sentence"]
ItemDifficulty = Literal["easy", "medium", "hard"]


class PronunciationItemResponse(BaseModel):
    id: uuid.UUID
    item_index: int
    text: str
    phonetic: str | None
    translation: str | None
    tips: str | None
    item_type: ItemType
    difficulty: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PronunciationSetResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    is_published: bool
    difficulty: str
    language: str
    folder_id: uuid.UUID | None = None
    item_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PronunciationSetDetailResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    is_published: bool
    difficulty: str
    language: str
    folder_id: uuid.UUID | None = None
    items: list[PronunciationItemResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class PronunciationSetUpdate(BaseModel):
    title: str | None = None


class PronunciationItemCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    item_type: ItemType = "word"
    phonetic: str | None = Field(default=None, max_length=500)
    translation: str | None = Field(default=None, max_length=1000)
    tips: str | None = Field(default=None, max_length=2000)
    difficulty: ItemDifficulty = "medium"


class PronunciationItemUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=1000)
    item_type: ItemType | None = None
    phonetic: str | None = Field(default=None, max_length=500)
    translation: str | None = Field(default=None, max_length=1000)
    tips: str | None = Field(default=None, max_length=2000)
    difficulty: ItemDifficulty | None = None


class PronunciationSetMove(BaseModel):
    folder_id: uuid.UUID | None = None


class PronunciationFolderResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PronunciationFolderCreate(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None


class PronunciationFolderRename(BaseModel):
    name: str


class PronunciationFolderMove(BaseModel):
    parent_id: uuid.UUID | None = None
