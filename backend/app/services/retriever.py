"""Retrieval service — pgvector-backed semantic search over document chunks."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk of text retrieved from the vector store."""

    chunk_id: uuid.UUID
    content: str
    document_id: uuid.UUID
    page_number: int | None
    similarity_score: float


async def retrieve_chunks(
    db: AsyncSession,
    course_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int = 10,
    document_ids: list[uuid.UUID] | None = None,
) -> list[RetrievedChunk]:
    """Return the *top_k* most similar chunks for *query_embedding*.

    Uses pgvector's ``<=>`` (cosine distance) operator and converts to
    cosine similarity via ``1 - distance``.
    """
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # 1 - cosine distance = cosine similarity
    similarity_expr = text(
        f"1 - (chunks.embedding <=> '{embedding_str}'::vector) AS similarity"
    )

    stmt = (
        select(Chunk, similarity_expr)
        .where(Chunk.course_id == course_id)
        .where(Chunk.embedding.isnot(None))
    )

    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))

    stmt = stmt.order_by(text("similarity DESC")).limit(top_k)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            content=chunk.content,
            document_id=chunk.document_id,
            page_number=chunk.page_number,
            similarity_score=float(similarity),
        )
        for chunk, similarity in rows
    ]
