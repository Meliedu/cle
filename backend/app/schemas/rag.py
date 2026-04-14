import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    course_id: uuid.UUID
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    search_mode: Literal["vector", "fulltext", "hybrid"] = "hybrid"
    document_ids: list[uuid.UUID] | None = None


class ChunkResult(BaseModel):
    chunk_id: uuid.UUID
    content: str
    document_id: uuid.UUID
    page_number: int | None
    similarity_score: float

    model_config = {"from_attributes": True}


class RAGQueryResponse(BaseModel):
    chunks: list[ChunkResult]


class GenerateQuizRequest(BaseModel):
    course_id: uuid.UUID
    title: str
    document_ids: list[uuid.UUID] | None = None
    num_questions: int = Field(default=5, ge=1, le=30)


class GenerateSummaryRequest(BaseModel):
    course_id: uuid.UUID
    document_ids: list[uuid.UUID] | None = None


class CourseSummaryResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    summary_text: str
    document_ids: list[uuid.UUID] | None
    generated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerateFlashcardsRequest(BaseModel):
    course_id: uuid.UUID
    title: str
    document_ids: list[uuid.UUID] | None = None
    num_cards: int = Field(default=10, ge=1, le=50)


# ---------------------------------------------------------------------------
# Async generation jobs
# ---------------------------------------------------------------------------

JobKind = Literal["generate_quiz", "generate_flashcards", "generate_summary"]
JobStatus = Literal["pending", "running", "completed", "failed"]


class JobAcceptedResponse(BaseModel):
    """Returned with HTTP 202 when a generation job has been enqueued."""

    job_id: uuid.UUID
    kind: JobKind
    status: JobStatus = "pending"
    course_id: uuid.UUID
    title: str | None = None


class JobStatusResponse(BaseModel):
    """Polled by the frontend to follow a generation job."""

    job_id: uuid.UUID
    kind: JobKind
    status: JobStatus
    course_id: uuid.UUID
    title: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
