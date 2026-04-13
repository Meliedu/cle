"""Retrieval service — pgvector-backed semantic search over document chunks."""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.chunk import Chunk
from app.models.document import Document


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

    Uses pgvector's cosine-distance operator via SQLAlchemy's bound-parameter
    mechanism (no raw-SQL interpolation of the embedding literal).
    """
    similarity = (1 - Chunk.embedding.cosine_distance(query_embedding)).label(
        "similarity"
    )

    # Join Document so soft-deleted documents' chunks drop out of results.
    stmt = (
        select(Chunk, similarity)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.course_id == course_id)
        .where(Chunk.embedding.isnot(None))
        .where(Document.deleted_at.is_(None))
    )

    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))

    stmt = stmt.order_by(similarity.desc()).limit(top_k)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            content=chunk.content,
            document_id=chunk.document_id,
            page_number=chunk.page_number,
            similarity_score=float(score),
        )
        for chunk, score in rows
    ]


async def fulltext_retrieve(
    db: AsyncSession,
    course_id: uuid.UUID,
    query: str,
    top_k: int = 10,
    document_ids: list[uuid.UUID] | None = None,
) -> list[RetrievedChunk]:
    """Full-text search using tsvector + ts_rank."""
    tsquery = func.plainto_tsquery("english", query)
    stmt = (
        select(
            Chunk.id,
            Chunk.content,
            Chunk.document_id,
            Chunk.page_number,
            func.ts_rank(Chunk.tsvector_content, tsquery).label("rank"),
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.course_id == course_id,
            Chunk.tsvector_content.op("@@")(tsquery),
            Document.deleted_at.is_(None),
        )
        .order_by(text("rank DESC"))
        .limit(top_k)
    )
    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))
    result = await db.execute(stmt)
    rows = result.all()
    return [
        RetrievedChunk(
            chunk_id=row.id,
            content=row.content,
            document_id=row.document_id,
            page_number=row.page_number,
            similarity_score=float(row.rank),
        )
        for row in rows
    ]


def rrf_merge(
    vector_results: list[RetrievedChunk],
    text_results: list[RetrievedChunk],
    k: int = 60,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion: merge two ranked lists."""
    scores: dict[uuid.UUID, float] = {}
    chunk_map: dict[uuid.UUID, RetrievedChunk] = {}
    for rank, chunk in enumerate(vector_results):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1.0 / (k + rank + 1)
        chunk_map[chunk.chunk_id] = chunk
    for rank, chunk in enumerate(text_results):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1.0 / (k + rank + 1)
        if chunk.chunk_id not in chunk_map:
            chunk_map[chunk.chunk_id] = chunk
    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]
    return [
        RetrievedChunk(
            chunk_id=chunk_map[cid].chunk_id,
            content=chunk_map[cid].content,
            document_id=chunk_map[cid].document_id,
            page_number=chunk_map[cid].page_number,
            similarity_score=scores[cid],
        )
        for cid in sorted_ids
    ]


# ---------------------------------------------------------------------------
# FlashRank reranker
# ---------------------------------------------------------------------------

_ranker = None
_ranker_lock = threading.Lock()


def _get_ranker():
    """Lazily initialize FlashRank with a double-checked lock so concurrent
    threads can't race the expensive model load and burn extra memory."""
    global _ranker
    if _ranker is None:
        with _ranker_lock:
            if _ranker is None:
                from flashrank import Ranker

                _ranker = Ranker(
                    model_name="ms-marco-MiniLM-L-12-v2",
                    cache_dir="/tmp/flashrank",
                )
    return _ranker


def _rerank_sync(
    query: str, chunks: list[RetrievedChunk], top_k: int
) -> list[RetrievedChunk]:
    from flashrank import RerankRequest

    ranker = _get_ranker()
    passages = [{"id": str(c.chunk_id), "text": c.content} for c in chunks]
    results = ranker.rerank(RerankRequest(query=query, passages=passages))

    chunk_map = {str(c.chunk_id): c for c in chunks}
    reranked: list[RetrievedChunk] = []
    for r in results[:top_k]:
        cid = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
        score = r.get("score") if isinstance(r, dict) else getattr(r, "score", 0.0)
        if cid and cid in chunk_map:
            c = chunk_map[cid]
            reranked.append(
                RetrievedChunk(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    document_id=c.document_id,
                    page_number=c.page_number,
                    similarity_score=float(score),
                )
            )
    return reranked


async def rerank_chunks(
    query: str, chunks: list[RetrievedChunk], top_k: int
) -> list[RetrievedChunk]:
    """Rerank chunks using FlashRank cross-encoder (runs in thread)."""
    if not chunks:
        return []
    return await asyncio.to_thread(_rerank_sync, query, chunks, top_k)


async def hybrid_retrieve(
    db: AsyncSession,
    course_id: uuid.UUID,
    query: str,
    query_embedding: list[float],
    top_k: int = 10,
    document_ids: list[uuid.UUID] | None = None,
) -> list[RetrievedChunk]:
    """Run vector + fulltext retrieval in parallel, merge via RRF, rerank.

    Each branch runs in its own session so the two queries use separate
    connections — SQLAlchemy's ``AsyncSession`` is not safe for concurrent
    query execution on a single session instance.
    """

    async def _vector() -> list[RetrievedChunk]:
        async with async_session_factory() as vs:
            return await retrieve_chunks(
                vs,
                course_id,
                query_embedding,
                top_k=top_k * 2,
                document_ids=document_ids,
            )

    async def _text() -> list[RetrievedChunk]:
        async with async_session_factory() as ts:
            return await fulltext_retrieve(
                ts,
                course_id,
                query,
                top_k=top_k * 2,
                document_ids=document_ids,
            )

    vector_results, text_results = await asyncio.gather(_vector(), _text())

    # RRF merge — fetch extra candidates for the reranker to pick from
    merged = rrf_merge(vector_results, text_results, k=60, top_k=top_k * 2)

    # Rerank the merged candidates down to final top_k
    return await rerank_chunks(query, merged, top_k)
