import uuid
from typing import Literal

from pydantic import BaseModel, Field


class WordScoreResponse(BaseModel):
    word: str
    accuracy: float
    error_type: str | None = None


class PronunciationGradeResponse(BaseModel):
    id: str
    overall_score: float
    accuracy_score: float
    fluency_score: float
    completeness_score: float
    prosody_score: float | None = None
    word_scores: list[WordScoreResponse]
    provider: str


class PronunciationHistoryEntry(BaseModel):
    id: str
    target_text: str
    overall_score: float
    accuracy_score: float
    fluency_score: float
    created_at: str


# Difficulty reuses the literal declared in app.schemas.rag — keep inline here
# to avoid a circular import chain in tests that mock rag.
SpeechDifficulty = Literal["easy", "medium", "hard", "mixed"]


class GeneratePromptsRequest(BaseModel):
    course_id: uuid.UUID
    num_prompts: int = Field(default=5, ge=1, le=10)
    difficulty: SpeechDifficulty = "medium"
    document_ids: list[uuid.UUID] | None = None


class PracticePromptResponse(BaseModel):
    target_text: str
