from pydantic import BaseModel


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
