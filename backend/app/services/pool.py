"""Revision pool replenishment — generates items for the adaptive difficulty pool."""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.course import Course
from app.models.revision import RevisionPoolItem
from app.services.embedder import embed_query
from app.services.generator import (
    generate_revision_flashcards,
    generate_revision_quiz,
    generate_revision_speaking,
)
from app.services.retriever import retrieve_chunks

logger = logging.getLogger(__name__)

DEFAULT_COUNTS: dict[str, int] = {"easy": 7, "medium": 7, "hard": 6}

_GENERATORS = {
    "quiz": generate_revision_quiz,
    "flashcard": generate_revision_flashcards,
    "speaking": generate_revision_speaking,
}


def _build_pool_item(
    course_id: uuid.UUID,
    content_type: str,
    difficulty: str,
    item: dict,
    language: str,
    source_chunk_id: uuid.UUID | None,
) -> RevisionPoolItem:
    """Create a RevisionPoolItem from a generated item dict."""
    if content_type == "quiz":
        return RevisionPoolItem(
            course_id=course_id,
            content_type=content_type,
            difficulty=difficulty,
            question_text=item.get("question_text"),
            options=item.get("options"),
            correct_answer=item.get("correct_answer"),
            explanation=item.get("explanation"),
            source_chunk_id=source_chunk_id,
        )
    elif content_type == "flashcard":
        return RevisionPoolItem(
            course_id=course_id,
            content_type=content_type,
            difficulty=difficulty,
            front=item.get("front"),
            back=item.get("back"),
            source_chunk_id=source_chunk_id,
        )
    elif content_type == "speaking":
        return RevisionPoolItem(
            course_id=course_id,
            content_type=content_type,
            difficulty=difficulty,
            target_text=item.get("target_text"),
            language=language,
            source_chunk_id=source_chunk_id,
        )
    else:
        raise ValueError(f"Unknown content_type: {content_type}")


async def replenish_pool(session: AsyncSession, payload: dict) -> None:
    """Generate revision pool items for a course.

    Parameters
    ----------
    session:
        Active async database session.
    payload:
        Task payload containing ``course_id``, ``content_type``, and
        optionally ``counts`` (mapping of difficulty -> count).
    """
    course_id = uuid.UUID(payload["course_id"])
    content_type: str = payload["content_type"]
    counts: dict[str, int] = payload.get("counts", DEFAULT_COUNTS)

    generator_fn = _GENERATORS.get(content_type)
    if generator_fn is None:
        raise ValueError(f"Unknown content_type: {content_type}")

    # Look up the course for its language setting
    result = await session.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    language = course.language if course else "english"

    # Build a general review embedding and retrieve context chunks
    query_embedding = await embed_query(f"general review material for {language} course")
    chunks = await retrieve_chunks(
        db=session,
        course_id=course_id,
        query_embedding=query_embedding,
        top_k=20,
    )

    context_texts = [c.content for c in chunks]
    source_chunk_id = chunks[0].chunk_id if chunks else None

    # Generate items for all difficulty levels concurrently
    difficulties = list(counts.keys())

    generation_results = await asyncio.gather(
        *(
            generator_fn(
                context=context_texts,
                difficulty=difficulty,
                count=counts[difficulty],
                language=language,
            )
            for difficulty in difficulties
        )
    )

    # Create RevisionPoolItem records from the results
    for difficulty, items in zip(difficulties, generation_results):
        for item in items:
            pool_item = _build_pool_item(
                course_id=course_id,
                content_type=content_type,
                difficulty=difficulty,
                item=item,
                language=language,
                source_chunk_id=source_chunk_id,
            )
            session.add(pool_item)

    await session.flush()
    logger.info(
        "Replenished pool for course=%s content_type=%s counts=%s",
        course_id,
        content_type,
        counts,
    )
