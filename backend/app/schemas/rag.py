import uuid

from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    course_id: uuid.UUID
    query: str
    top_k: int = Field(default=10, ge=1, le=50)


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


class GenerateFlashcardsRequest(BaseModel):
    course_id: uuid.UUID
    title: str
    document_ids: list[uuid.UUID] | None = None
    num_cards: int = Field(default=10, ge=1, le=50)
