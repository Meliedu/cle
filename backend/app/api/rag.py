import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment as _verify_enrollment
from app.api.deps import get_current_user, get_db, require_instructor
from app.models.course import Course
from app.models.summary import CourseSummary
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.rag import (
    ChunkResult,
    CourseSummaryResponse,
    GenerateFlashcardsRequest,
    GeneratePronunciationRequest,
    GenerateQuizRequest,
    GenerateSummaryRequest,
    JobAcceptedResponse,
    JobStatusResponse,
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.services.embedder import embed_query
from app.services.retriever import fulltext_retrieve, hybrid_retrieve, retrieve_chunks
from app.utils.sanitize import sanitize_query as _sanitize_query

router = APIRouter(prefix="/rag", tags=["rag"])


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

    if body.document_ids:
        from app.models.document import Document
        result = await db.execute(
            select(Document.id).where(
                Document.id.in_(body.document_ids),
                Document.course_id == body.course_id,
                Document.deleted_at.is_(None),
            )
        )
        owned_ids = {row[0] for row in result.all()}
        missing = set(body.document_ids) - owned_ids
        if missing:
            raise HTTPException(
                status_code=400,
                detail="One or more document_ids do not belong to this course",
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


async def _enqueue_generation_job(
    db: AsyncSession,
    *,
    task_type: str,
    course_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str | None,
    extra: dict,
) -> Task:
    """Create a Task row that the background worker will pick up."""
    payload = {
        "course_id": str(course_id),
        "user_id": str(user_id),
        **({"title": title} if title is not None else {}),
        **extra,
    }
    task = Task(task_type=task_type, payload=payload)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


def _task_to_status_response(task: Task) -> JobStatusResponse:
    payload = task.payload or {}
    course_id = uuid.UUID(payload["course_id"]) if payload.get("course_id") else None
    title = payload.get("title")
    result = payload.get("result")
    return JobStatusResponse(
        job_id=task.id,
        kind=task.task_type,  # type: ignore[arg-type]
        status=task.status,  # type: ignore[arg-type]
        course_id=course_id,  # type: ignore[arg-type]
        title=title,
        result=result if isinstance(result, dict) else None,
        error=task.error_message,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


@router.post(
    "/generate-quiz",
    response_model=APIResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def rag_generate_quiz(
    body: GenerateQuizRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_enrollment(db, body.course_id, user.id)
    await _get_course_language(db, body.course_id)  # validates course exists

    task = await _enqueue_generation_job(
        db,
        task_type="generate_quiz",
        course_id=body.course_id,
        user_id=user.id,
        title=body.title,
        extra={
            "num_questions": body.num_questions,
            "document_ids": [str(d) for d in (body.document_ids or [])] or None,
            "purpose": body.purpose,
            "question_types": body.question_types,
            "mcq_option_count": body.mcq_option_count,
            "difficulty": body.difficulty,
        },
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return APIResponse(
        success=True,
        data=JobAcceptedResponse(
            job_id=task.id,
            kind="generate_quiz",
            course_id=body.course_id,
            title=body.title,
        ),
    )


@router.post(
    "/generate-summary",
    response_model=APIResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def rag_generate_summary(
    body: GenerateSummaryRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
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

    task = await _enqueue_generation_job(
        db,
        task_type="generate_summary",
        course_id=body.course_id,
        user_id=user.id,
        title=None,
        extra={
            "document_ids": [str(d) for d in (body.document_ids or [])] or None,
        },
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return APIResponse(
        success=True,
        data=JobAcceptedResponse(
            job_id=task.id,
            kind="generate_summary",
            course_id=body.course_id,
        ),
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
    response_model=APIResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def rag_generate_flashcards(
    body: GenerateFlashcardsRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Spec: any enrolled student may generate a flashcard set for their course.
    await _verify_enrollment(db, body.course_id, user.id)
    await _get_course_language(db, body.course_id)

    task = await _enqueue_generation_job(
        db,
        task_type="generate_flashcards",
        course_id=body.course_id,
        user_id=user.id,
        title=body.title,
        extra={
            "num_cards": body.num_cards,
            "document_ids": [str(d) for d in (body.document_ids or [])] or None,
            "difficulty": body.difficulty,
        },
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return APIResponse(
        success=True,
        data=JobAcceptedResponse(
            job_id=task.id,
            kind="generate_flashcards",
            course_id=body.course_id,
            title=body.title,
        ),
    )


@router.post(
    "/generate-pronunciation",
    response_model=APIResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def rag_generate_pronunciation(
    body: GeneratePronunciationRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    # Pronunciation sets are instructor-curated and follow a publish lifecycle,
    # so generation is restricted to instructors (mirrors quiz, not flashcards).
    await _verify_enrollment(db, body.course_id, user.id)
    await _get_course_language(db, body.course_id)

    task = await _enqueue_generation_job(
        db,
        task_type="generate_pronunciation",
        course_id=body.course_id,
        user_id=user.id,
        title=body.title,
        extra={
            "num_items": body.num_items,
            "document_ids": [str(d) for d in (body.document_ids or [])] or None,
            "difficulty": body.difficulty,
            "item_types": list(body.item_types),
        },
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return APIResponse(
        success=True,
        data=JobAcceptedResponse(
            job_id=task.id,
            kind="generate_pronunciation",
            course_id=body.course_id,
            title=body.title,
        ),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=APIResponse[JobStatusResponse],
)
async def rag_get_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Poll the status of a generation job.

    Ownership is enforced by matching the caller's user_id against the value
    stored in ``payload.user_id`` at enqueue time.
    """
    row = await db.execute(select(Task).where(Task.id == job_id))
    task = row.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if task.task_type not in {
        "generate_quiz",
        "generate_flashcards",
        "generate_pronunciation",
        "generate_summary",
    }:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = task.payload or {}
    if str(payload.get("user_id")) != str(user.id):
        # Do not leak existence of another user's job.
        raise HTTPException(status_code=404, detail="Job not found")

    return APIResponse(success=True, data=_task_to_status_response(task))
