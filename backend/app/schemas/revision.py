from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StartRevisionRequest(BaseModel):
    content_type: Literal["quiz", "flashcard", "speaking"]


class RevisionQuizItem(BaseModel):
    pool_item_id: str
    content_type: Literal["quiz"] = "quiz"
    question_text: str
    options: dict[str, str]


class RevisionFlashcardItem(BaseModel):
    pool_item_id: str
    content_type: Literal["flashcard"] = "flashcard"
    front: str
    back: str


class RevisionSpeakingItem(BaseModel):
    pool_item_id: str
    content_type: Literal["speaking"] = "speaking"
    target_text: str
    language: str


RevisionItem = RevisionQuizItem | RevisionFlashcardItem | RevisionSpeakingItem


class StartRevisionResponse(BaseModel):
    session_id: str
    status: Literal["ready", "preparing"]
    first_item: RevisionItem | None = None


class SubmitAnswerRequest(BaseModel):
    pool_item_id: UUID
    answer: str | None = None  # quiz: option letter (A/B/C/D)
    quality: int | None = Field(None, ge=0, le=5)  # flashcard: SM-2 quality
    pronunciation_score: float | None = None  # speaking: 0-100 from grading
    time_taken_ms: int | None = None


class SessionStats(BaseModel):
    items_answered: int
    accuracy: float
    current_streak: int


class SubmitAnswerResponse(BaseModel):
    score: float
    is_correct: bool | None = None  # quiz only
    correct_answer: str | None = None  # quiz only
    explanation: str | None = None  # quiz only
    next_item: RevisionItem | None = None
    session_stats: SessionStats


class EndSessionResponse(BaseModel):
    items_answered: int
    average_score: float
    scores_by_difficulty: dict[str, float]
    duration_seconds: int
