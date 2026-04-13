import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.models.course import Course, Enrollment
from app.models.flashcard import FlashcardCard, FlashcardSet, FlashcardSetDocument
from app.models.quiz import Question, Quiz, QuizDocument
from app.models.summary import CourseSummary
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.flashcard import FlashcardCardResponse, FlashcardSetDetailResponse
from app.schemas.quiz import QuestionResponse, QuizDetailResponse
from app.schemas.rag import (
    ChunkResult,
    CourseSummaryResponse,
    GenerateFlashcardsRequest,
    GenerateQuizRequest,
    GenerateSummaryRequest,
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.services.embedder import embed_query
from app.services.generator import generate_flashcards, generate_quiz, generate_summary
from app.services.retriever import fulltext_retrieve, hybrid_retrieve, retrieve_chunks

router = APIRouter(prefix="/rag", tags=["rag"])

_MAX_QUERY_CHARS = 2000
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_query(raw: str) -> str:
    """Strip control characters and bound length before feeding user text to
    the LLM. Defence in depth against prompt injection payloads delivered via
    the ``query``/``title`` fields (these get interpolated into LLM prompts)."""
    cleaned = _CONTROL_CHARS_RE.sub(" ", raw or "")
    cleaned = cleaned.strip()
    if len(cleaned) > _MAX_QUERY_CHARS:
        cleaned = cleaned[:_MAX_QUERY_CHARS]
    return cleaned


async def _verify_enrollment(
    db: AsyncSession,
    course_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Check that the user is enrolled in the course. Raises 403 if not."""
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enrolled in this course",
        )


async def _get_course_language(db: AsyncSession, course_id: uuid.UUID) -> str:
    """Return the course language, or raise 404 if course not found."""
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    return course.language


@router.post("/query", response_model=APIResponse[RAGQueryResponse])
async def rag_query(
    body: RAGQueryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, body.course_id, user.id)

    safe_query = _sanitize_query(body.query)
    if not safe_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query is empty after sanitization",
        )

    if body.search_mode == "fulltext":
        chunks = await fulltext_retrieve(
            db,
            course_id=body.course_id,
            query=safe_query,
            top_k=body.top_k,
            document_ids=body.document_ids,
        )
    elif body.search_mode == "vector":
        query_embedding = await embed_query(safe_query)
        chunks = await retrieve_chunks(
            db,
            course_id=body.course_id,
            query_embedding=query_embedding,
            top_k=body.top_k,
            document_ids=body.document_ids,
        )
    else:  # hybrid (default)
        query_embedding = await embed_query(safe_query)
        chunks = await hybrid_retrieve(
            db,
            course_id=body.course_id,
            query=safe_query,
            query_embedding=query_embedding,
            top_k=body.top_k,
            document_ids=body.document_ids,
        )

    chunk_results = [
        ChunkResult(
            chunk_id=c.chunk_id,
            content=c.content,
            document_id=c.document_id,
            page_number=c.page_number,
            similarity_score=c.similarity_score,
        )
        for c in chunks
    ]

    return APIResponse(success=True, data=RAGQueryResponse(chunks=chunk_results))


@router.post("/generate-quiz", response_model=APIResponse[QuizDetailResponse])
async def rag_generate_quiz(
    body: GenerateQuizRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    import logging
    log = logging.getLogger(__name__)

    await _verify_enrollment(db, body.course_id, user.id)
    language = await _get_course_language(db, body.course_id)

    safe_title = _sanitize_query(body.title)
    log.info("generate-quiz: embedding query '%s'", safe_title)
    query_embedding = await embed_query(safe_title)

    log.info("generate-quiz: retrieving chunks (doc_ids=%s)", body.document_ids)
    chunks = await retrieve_chunks(
        db,
        course_id=body.course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=body.document_ids,
    )
    log.info("generate-quiz: got %d chunks", len(chunks))

    log.info("generate-quiz: calling LLM for %d questions", body.num_questions)
    generated = await generate_quiz(
        chunks,
        num_questions=body.num_questions,
        language=language,
    )
    log.info("generate-quiz: LLM returned %d questions", len(generated))

    quiz = Quiz(
        course_id=body.course_id,
        created_by=user.id,
        title=body.title,
        quiz_type="multiple_choice",
        is_published=False,
    )
    db.add(quiz)
    await db.flush()

    questions: list[Question] = []
    for idx, gq in enumerate(generated):
        question = Question(
            quiz_id=quiz.id,
            question_index=idx,
            type="multiple_choice",
            question_text=gq.question_text,
            options=gq.options,
            correct_answer=gq.correct_answer,
            explanation=gq.explanation,
        )
        db.add(question)
        questions.append(question)

    if body.document_ids:
        for doc_id in body.document_ids:
            db.add(QuizDocument(quiz_id=quiz.id, document_id=doc_id))

    await db.commit()
    await db.refresh(quiz)

    question_responses = [
        QuestionResponse(
            id=q.id,
            question_index=q.question_index,
            type=q.type,
            question_text=q.question_text,
            options=q.options,
            explanation=q.explanation,
        )
        for q in questions
    ]

    return APIResponse(
        success=True,
        data=QuizDetailResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            is_published=quiz.is_published,
            questions=question_responses,
            created_at=quiz.created_at,
        ),
    )


@router.post(
    "/generate-summary", response_model=APIResponse[CourseSummaryResponse]
)
async def rag_generate_summary(
    body: GenerateSummaryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    # Summary is a course-wide artifact; only the instructor can (re)generate it.
    # Students see the persisted result inline on the course overview.
    course_result = await db.execute(
        select(Course).where(
            Course.id == body.course_id, Course.deleted_at.is_(None)
        )
    )
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    if course.instructor_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the course instructor can generate a summary",
        )

    query_embedding = await embed_query("comprehensive summary of all material")
    chunks = await retrieve_chunks(
        db,
        course_id=body.course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=body.document_ids,
    )

    summary_text = await generate_summary(chunks, language=course.language)

    existing = await db.execute(
        select(CourseSummary).where(CourseSummary.course_id == body.course_id)
    )
    record = existing.scalar_one_or_none()
    doc_ids_json = (
        [str(d) for d in body.document_ids] if body.document_ids else None
    )
    if record is None:
        record = CourseSummary(
            course_id=body.course_id,
            summary_text=summary_text,
            document_ids=doc_ids_json,
            generated_by=user.id,
        )
        db.add(record)
    else:
        record.summary_text = summary_text
        record.document_ids = doc_ids_json
        record.generated_by = user.id
    await db.commit()
    await db.refresh(record)

    return APIResponse(
        success=True, data=CourseSummaryResponse.model_validate(record)
    )


@router.get(
    "/course-summary/{course_id}",
    response_model=APIResponse[CourseSummaryResponse | None],
)
async def rag_get_course_summary(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Any enrolled user (student or instructor) can read the persisted summary.
    await _verify_enrollment(db, course_id, user.id)

    result = await db.execute(
        select(CourseSummary).where(CourseSummary.course_id == course_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return APIResponse(success=True, data=None)
    return APIResponse(
        success=True, data=CourseSummaryResponse.model_validate(record)
    )


@router.post(
    "/generate-flashcards",
    response_model=APIResponse[FlashcardSetDetailResponse],
)
async def rag_generate_flashcards(
    body: GenerateFlashcardsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Spec: any enrolled student may generate a flashcard set for their course.
    await _verify_enrollment(db, body.course_id, user.id)
    language = await _get_course_language(db, body.course_id)

    safe_title = _sanitize_query(body.title)
    query_embedding = await embed_query(safe_title)
    chunks = await retrieve_chunks(
        db,
        course_id=body.course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=body.document_ids,
    )

    generated = await generate_flashcards(
        chunks,
        num_cards=body.num_cards,
        language=language,
    )

    fc_set = FlashcardSet(
        course_id=body.course_id,
        created_by=user.id,
        title=body.title,
        is_published=False,
    )
    db.add(fc_set)
    await db.flush()

    cards: list[FlashcardCard] = []
    for idx, gc in enumerate(generated):
        card = FlashcardCard(
            flashcard_set_id=fc_set.id,
            card_index=idx,
            front=gc.front,
            back=gc.back,
        )
        db.add(card)
        cards.append(card)

    if body.document_ids:
        for doc_id in body.document_ids:
            db.add(FlashcardSetDocument(flashcard_set_id=fc_set.id, document_id=doc_id))

    await db.commit()
    await db.refresh(fc_set)

    card_responses = [
        FlashcardCardResponse(
            id=c.id,
            card_index=c.card_index,
            front=c.front,
            back=c.back,
            created_at=c.created_at,
        )
        for c in cards
    ]

    return APIResponse(
        success=True,
        data=FlashcardSetDetailResponse(
            id=fc_set.id,
            course_id=fc_set.course_id,
            title=fc_set.title,
            is_published=fc_set.is_published,
            cards=card_responses,
            created_at=fc_set.created_at,
        ),
    )
