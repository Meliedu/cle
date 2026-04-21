"""Async generation jobs.

These handlers encapsulate the work previously performed synchronously inside
``app.api.rag``. They are invoked by ``worker.py`` after a user enqueues a
task via ``POST /rag/generate-*`` and return a small ``result`` dict that the
worker writes back into ``Task.payload["result"]`` so the HTTP polling
endpoint can surface it to the frontend.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.flashcard import FlashcardCard, FlashcardSet, FlashcardSetDocument
from app.models.quiz import Question, Quiz, QuizDocument
from app.models.summary import CourseSummary
from app.schemas.rag import (
    GenerateFlashcardsRequest,
    GenerateQuizRequest,
    GenerateSummaryRequest,
)
from app.services.embedder import embed_query
from app.services.generator import (
    generate_flashcards,
    generate_quiz,
    generate_summary,
)
from app.services.retriever import retrieve_chunks
from app.utils.sanitize import sanitize_query as _sanitize

logger = logging.getLogger(__name__)


async def _course_language(session: AsyncSession, course_id: uuid.UUID) -> str:
    row = await session.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = row.scalar_one_or_none()
    if course is None:
        raise ValueError(f"Course {course_id} not found")
    return course.language


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def run_generate_quiz(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    # Re-validate payload via the same Pydantic schema used at the HTTP edge so
    # that constraints (bounds on num_questions/mcq_option_count, literal sets
    # for purpose/difficulty/question_types) hold even if the payload was
    # tampered with between enqueue and dequeue.
    validated = GenerateQuizRequest.model_validate(
        {
            "course_id": payload["course_id"],
            "title": payload["title"],
            "document_ids": payload.get("document_ids"),
            "num_questions": payload.get("num_questions", 5),
            "purpose": payload.get("purpose", "after_class"),
            # Schema guarantees min_length=1 with a default; the .get() default
            # is belt-and-suspenders only.
            "question_types": payload.get("question_types", ["multiple_choice"]),
            "mcq_option_count": payload.get("mcq_option_count", 4),
            "difficulty": payload.get("difficulty", "medium"),
        }
    )
    course_id = validated.course_id
    user_id = uuid.UUID(payload["user_id"])
    title = validated.title
    num_questions = validated.num_questions
    document_uuids = list(validated.document_ids) if validated.document_ids else None
    purpose = validated.purpose
    question_types = list(validated.question_types)
    mcq_option_count = validated.mcq_option_count
    difficulty = validated.difficulty

    language = await _course_language(session, course_id)
    safe_title = _sanitize(title)

    query_embedding = await embed_query(safe_title)
    chunks = await retrieve_chunks(
        session,
        course_id=course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=document_uuids,
    )
    generated = await generate_quiz(
        chunks,
        num_questions=num_questions,
        language=language,
        question_types=question_types,
        mcq_option_count=mcq_option_count,
        difficulty=difficulty,
    )

    quiz = Quiz(
        course_id=course_id,
        created_by=user_id,
        title=title,
        quiz_type="multiple_choice",
        purpose=purpose,
        is_published=(purpose == "live"),
    )
    session.add(quiz)
    await session.flush()

    for idx, gq in enumerate(generated):
        session.add(
            Question(
                quiz_id=quiz.id,
                question_index=idx,
                type=gq.type,
                question_text=gq.question_text,
                options=gq.options,
                correct_answer=gq.correct_answer,
                explanation=gq.explanation,
                difficulty=gq.difficulty,
            )
        )

    if document_uuids:
        for doc_id in document_uuids:
            session.add(QuizDocument(quiz_id=quiz.id, document_id=doc_id))

    await session.flush()
    logger.info("generate_quiz job finished quiz_id=%s questions=%d", quiz.id, len(generated))
    return {"quiz_id": str(quiz.id), "question_count": len(generated)}


async def run_generate_flashcards(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    # Default difficulty to "medium" when missing so tasks enqueued before
    # the difficulty field was added keep flowing through the worker.
    validated = GenerateFlashcardsRequest.model_validate(
        {
            "course_id": payload["course_id"],
            "title": payload["title"],
            "document_ids": payload.get("document_ids"),
            "num_cards": payload.get("num_cards", 10),
            "difficulty": payload.get("difficulty", "medium"),
        }
    )
    course_id = validated.course_id
    user_id = uuid.UUID(payload["user_id"])
    title = validated.title
    num_cards = validated.num_cards
    document_uuids = list(validated.document_ids) if validated.document_ids else None
    difficulty = validated.difficulty

    language = await _course_language(session, course_id)
    safe_title = _sanitize(title)

    query_embedding = await embed_query(safe_title)
    chunks = await retrieve_chunks(
        session,
        course_id=course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=document_uuids,
    )
    generated = await generate_flashcards(
        chunks,
        num_cards=num_cards,
        language=language,
        difficulty=difficulty,
    )

    fc_set = FlashcardSet(
        course_id=course_id,
        created_by=user_id,
        title=title,
        is_published=False,
    )
    session.add(fc_set)
    await session.flush()

    # Flashcards generated at mixed difficulty are stored as "medium" per-card
    # since the generator doesn't currently emit a per-card difficulty. A
    # specific-difficulty run tags all cards with that difficulty.
    card_difficulty = difficulty if difficulty != "mixed" else "medium"
    for idx, gc in enumerate(generated):
        session.add(
            FlashcardCard(
                flashcard_set_id=fc_set.id,
                card_index=idx,
                front=gc.front,
                back=gc.back,
                difficulty=card_difficulty,
            )
        )

    if document_uuids:
        for doc_id in document_uuids:
            session.add(
                FlashcardSetDocument(flashcard_set_id=fc_set.id, document_id=doc_id)
            )

    await session.flush()
    logger.info(
        "generate_flashcards job finished set_id=%s cards=%d", fc_set.id, len(generated)
    )
    return {"flashcard_set_id": str(fc_set.id), "card_count": len(generated)}


async def run_generate_summary(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    validated = GenerateSummaryRequest.model_validate(
        {
            "course_id": payload["course_id"],
            "document_ids": payload.get("document_ids"),
        }
    )
    course_id = validated.course_id
    user_id = uuid.UUID(payload["user_id"])
    document_uuids = list(validated.document_ids) if validated.document_ids else None

    language = await _course_language(session, course_id)

    query_embedding = await embed_query("comprehensive summary of all material")
    chunks = await retrieve_chunks(
        session,
        course_id=course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=document_uuids,
    )
    summary_text = await generate_summary(chunks, language=language)

    existing = await session.execute(
        select(CourseSummary).where(CourseSummary.course_id == course_id)
    )
    record = existing.scalar_one_or_none()
    doc_ids_json = [str(d) for d in document_uuids] if document_uuids else None
    if record is None:
        record = CourseSummary(
            course_id=course_id,
            summary_text=summary_text,
            document_ids=doc_ids_json,
            generated_by=user_id,
        )
        session.add(record)
    else:
        record.summary_text = summary_text
        record.document_ids = doc_ids_json
        record.generated_by = user_id

    await session.flush()
    logger.info("generate_summary job finished course_id=%s", course_id)
    return {"course_id": str(course_id), "summary_id": str(record.id)}


_HANDLERS = {
    "generate_quiz": run_generate_quiz,
    "generate_flashcards": run_generate_flashcards,
    "generate_summary": run_generate_summary,
}


async def run_generation_job(
    session: AsyncSession, task_type: str, payload: dict[str, Any]
) -> dict[str, Any]:
    handler = _HANDLERS.get(task_type)
    if handler is None:
        raise ValueError(f"Unknown generation task type: {task_type}")
    return await handler(session, payload)
