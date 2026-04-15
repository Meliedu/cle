import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api._helpers import verify_enrollment as _verify_enrollment
from app.api.deps import get_current_user, get_db, require_instructor
from app.models.quiz import Question, Quiz, QuizAttempt, QuizDocument, QuizFolder
from app.models.user import User
from app.schemas.common import APIResponse
from app.services.gamification import award_xp
from app.schemas.quiz import (
    QuestionCreate,
    QuestionResponse,
    QuestionWithAnswerResponse,
    QuizAttemptCreate,
    QuizAttemptResponse,
    QuizAttemptResult,
    QuizDetailResponse,
    QuizFolderCreate,
    QuizFolderMove,
    QuizFolderRename,
    QuizFolderResponse,
    QuizMove,
    QuizPreviewResponse,
    QuizResponse,
    QuizUpdate,
)

router = APIRouter(tags=["quizzes"])


@router.get(
    "/courses/{course_id}/quizzes",
    response_model=APIResponse[list[QuizResponse]],
)
async def list_quizzes(
    course_id: uuid.UUID,
    purpose: Literal["after_class", "live"] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, course_id, user.id)

    stmt = (
        select(
            Quiz,
            func.count(Question.id).label("question_count"),
        )
        .outerjoin(Question, Question.quiz_id == Quiz.id)
        .where(Quiz.course_id == course_id, Quiz.deleted_at.is_(None))
        .group_by(Quiz.id)
    )

    if purpose is not None:
        stmt = stmt.where(Quiz.purpose == purpose)

    if user.role != "instructor":
        stmt = stmt.where(Quiz.is_published.is_(True))

    result = await db.execute(stmt)
    rows = result.all()

    data = [
        QuizResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            purpose=quiz.purpose,
            folder_id=quiz.folder_id,
            is_published=quiz.is_published,
            question_count=question_count,
            created_at=quiz.created_at,
        )
        for quiz, question_count in rows
    ]

    return APIResponse(success=True, data=data)


@router.get(
    "/quizzes/{quiz_id}",
    response_model=APIResponse[QuizDetailResponse],
)
async def get_quiz(
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Quiz)
        .options(selectinload(Quiz.questions))
        .where(Quiz.id == quiz_id, Quiz.deleted_at.is_(None))
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    await _verify_enrollment(db, quiz.course_id, user.id)

    if user.role != "instructor" and not quiz.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    question_responses = [
        QuestionResponse(
            id=q.id,
            question_index=q.question_index,
            type=q.type,
            question_text=q.question_text,
            options=q.options,
            explanation=q.explanation,
        )
        for q in quiz.questions
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


@router.get(
    "/quizzes/{quiz_id}/preview",
    response_model=APIResponse[QuizPreviewResponse],
)
async def preview_quiz(
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Quiz)
        .options(selectinload(Quiz.questions))
        .where(Quiz.id == quiz_id, Quiz.deleted_at.is_(None))
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    await _verify_enrollment(db, quiz.course_id, user.id)

    question_responses = [
        QuestionWithAnswerResponse(
            id=q.id,
            question_index=q.question_index,
            type=q.type,
            question_text=q.question_text,
            options=q.options,
            explanation=q.explanation,
            correct_answer=q.correct_answer,
        )
        for q in quiz.questions
    ]

    return APIResponse(
        success=True,
        data=QuizPreviewResponse(
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


@router.put(
    "/quizzes/{quiz_id}",
    response_model=APIResponse[QuizResponse],
)
async def update_quiz(
    quiz_id: uuid.UUID,
    body: QuizUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.created_by == user.id,
            Quiz.deleted_at.is_(None),
        )
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(quiz, field, value)

    await db.commit()
    await db.refresh(quiz)

    count_result = await db.execute(
        select(func.count(Question.id)).where(Question.quiz_id == quiz.id)
    )
    question_count = count_result.scalar_one()

    return APIResponse(
        success=True,
        data=QuizResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            purpose=quiz.purpose,
            folder_id=quiz.folder_id,
            is_published=quiz.is_published,
            question_count=question_count,
            created_at=quiz.created_at,
        ),
    )


@router.delete(
    "/quizzes/{quiz_id}",
    response_model=APIResponse[None],
)
async def delete_quiz(
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.created_by == user.id,
            Quiz.deleted_at.is_(None),
        )
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    quiz.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.post(
    "/quizzes/{quiz_id}/publish",
    response_model=APIResponse[QuizResponse],
)
async def publish_quiz(
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.created_by == user.id,
            Quiz.deleted_at.is_(None),
        )
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    quiz.is_published = not quiz.is_published
    await db.commit()
    await db.refresh(quiz)

    count_result = await db.execute(
        select(func.count(Question.id)).where(Question.quiz_id == quiz.id)
    )
    question_count = count_result.scalar_one()

    return APIResponse(
        success=True,
        data=QuizResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            purpose=quiz.purpose,
            folder_id=quiz.folder_id,
            is_published=quiz.is_published,
            question_count=question_count,
            created_at=quiz.created_at,
        ),
    )


@router.delete(
    "/questions/{question_id}",
    response_model=APIResponse[None],
)
async def delete_question(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Question)
        .join(Quiz, Quiz.id == Question.quiz_id)
        .where(
            Question.id == question_id,
            Quiz.created_by == user.id,
            Quiz.deleted_at.is_(None),
        )
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    await db.delete(question)

    # Reindex remaining questions
    remaining = await db.execute(
        select(Question)
        .where(Question.quiz_id == question.quiz_id)
        .order_by(Question.question_index)
    )
    for idx, q in enumerate(remaining.scalars().all()):
        q.question_index = idx

    await db.commit()
    return APIResponse(success=True, data=None)


@router.post(
    "/quizzes/{quiz_id}/questions",
    response_model=APIResponse[QuestionWithAnswerResponse],
    status_code=201,
)
async def add_question(
    quiz_id: uuid.UUID,
    body: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.created_by == user.id,
            Quiz.deleted_at.is_(None),
        )
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    # Determine next question index
    count_result = await db.execute(
        select(func.count(Question.id)).where(Question.quiz_id == quiz_id)
    )
    next_index = count_result.scalar_one()

    question = Question(
        quiz_id=quiz_id,
        question_index=next_index,
        type="multiple_choice",
        question_text=body.question_text,
        options=body.options,
        correct_answer=body.correct_answer,
        explanation=body.explanation,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)

    return APIResponse(
        success=True,
        data=QuestionWithAnswerResponse(
            id=question.id,
            question_index=question.question_index,
            type=question.type,
            question_text=question.question_text,
            options=question.options,
            explanation=question.explanation,
            correct_answer=question.correct_answer,
        ),
    )


@router.post(
    "/questions/{question_id}/regenerate",
    response_model=APIResponse[QuestionWithAnswerResponse],
)
async def regenerate_question(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    from app.services.embedder import embed_query
    from app.services.generator import generate_quiz
    from app.services.retriever import retrieve_chunks

    result = await db.execute(
        select(Question)
        .join(Quiz, Quiz.id == Question.quiz_id)
        .where(
            Question.id == question_id,
            Quiz.created_by == user.id,
            Quiz.deleted_at.is_(None),
        )
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    # Get quiz and course language
    quiz_result = await db.execute(
        select(Quiz).options(selectinload(Quiz.source_documents)).where(Quiz.id == question.quiz_id)
    )
    quiz = quiz_result.scalar_one()

    from app.models.course import Course
    course_result = await db.execute(select(Course).where(Course.id == quiz.course_id))
    course = course_result.scalar_one()

    # Get document IDs from the quiz's source docs
    doc_ids = [qd.document_id for qd in quiz.source_documents] or None

    # Retrieve chunks and generate 1 replacement question
    query_embedding = await embed_query(question.question_text)
    chunks = await retrieve_chunks(
        db,
        course_id=quiz.course_id,
        query_embedding=query_embedding,
        top_k=10,
        document_ids=doc_ids,
    )

    generated = await generate_quiz(chunks, num_questions=1, language=course.language)
    if not generated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate question",
        )

    new_q = generated[0]
    question.question_text = new_q.question_text
    question.options = new_q.options
    question.correct_answer = new_q.correct_answer
    question.explanation = new_q.explanation

    await db.commit()
    await db.refresh(question)

    return APIResponse(
        success=True,
        data=QuestionWithAnswerResponse(
            id=question.id,
            question_index=question.question_index,
            type=question.type,
            question_text=question.question_text,
            options=question.options,
            explanation=question.explanation,
            correct_answer=question.correct_answer,
        ),
    )


@router.post(
    "/quizzes/{quiz_id}/attempt",
    response_model=APIResponse[QuizAttemptResponse],
    status_code=201,
)
async def submit_attempt(
    quiz_id: uuid.UUID,
    body: QuizAttemptCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Quiz)
        .options(selectinload(Quiz.questions))
        .where(
            Quiz.id == quiz_id,
            Quiz.deleted_at.is_(None),
        )
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    await _verify_enrollment(db, quiz.course_id, user.id)

    # Unpublished quizzes can only be attempted by their creator (for preview)
    if not quiz.is_published and quiz.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    total_questions = len(quiz.questions)
    correct_count = 0
    results: list[QuizAttemptResult] = []

    for question in quiz.questions:
        q_id_str = str(question.id)
        selected = body.answers.get(q_id_str, "")
        is_correct = selected == question.correct_answer
        if is_correct:
            correct_count += 1

        results.append(
            QuizAttemptResult(
                question_id=question.id,
                question_text=question.question_text,
                selected_answer=selected,
                correct_answer=question.correct_answer,
                is_correct=is_correct,
                explanation=question.explanation,
            )
        )

    score = (
        Decimal(correct_count * 100) / Decimal(total_questions)
        if total_questions > 0
        else Decimal(0)
    )
    score = score.quantize(Decimal("0.01"))
    now = datetime.now(timezone.utc)

    attempt = QuizAttempt(
        quiz_id=quiz_id,
        user_id=user.id,
        answers=body.answers,
        score=score,
        total_questions=total_questions,
        correct_count=correct_count,
        time_taken_seconds=body.time_taken_seconds,
        completed_at=now,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    # Award XP for quiz attempt
    xp = int(attempt.score * 10)
    await award_xp(
        db,
        user_id=user.id,
        course_id=quiz.course_id,
        xp=xp,
        activity="quiz",
        quiz_score=float(attempt.score),
        quiz_time_seconds=attempt.time_taken_seconds,
    )
    await db.commit()

    return APIResponse(
        success=True,
        data=QuizAttemptResponse(
            id=attempt.id,
            quiz_id=attempt.quiz_id,
            score=attempt.score,
            total_questions=attempt.total_questions,
            correct_count=attempt.correct_count,
            time_taken_seconds=attempt.time_taken_seconds,
            results=results,
            completed_at=attempt.completed_at,
        ),
    )


# ---------------------------------------------------------------------------
# Import to live question bank
# ---------------------------------------------------------------------------


class ImportToLiveRequest(BaseModel):
    source_quiz_id: uuid.UUID
    question_ids: list[uuid.UUID] = Field(default_factory=list)
    title: str = Field(min_length=1, max_length=255)


@router.post(
    "/courses/{course_id}/quizzes/import-to-live",
    response_model=APIResponse[QuizResponse],
    status_code=status.HTTP_201_CREATED,
)
async def import_to_live(
    course_id: uuid.UUID,
    body: ImportToLiveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    """Copy selected questions from an existing quiz into a new live-purpose quiz.

    The new quiz is created published (live bank entries are directly usable) and
    marked purpose='live'. Source quiz is untouched.
    """
    await _verify_enrollment(db, course_id, user.id)

    source = await db.get(Quiz, body.source_quiz_id)
    if (
        source is None
        or source.deleted_at is not None
        or source.course_id != course_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source quiz not found in this course",
        )

    q_stmt = select(Question).where(Question.quiz_id == source.id)
    if body.question_ids:
        q_stmt = q_stmt.where(Question.id.in_(body.question_ids))
    q_stmt = q_stmt.order_by(Question.question_index)
    source_questions = (await db.execute(q_stmt)).scalars().all()

    if not source_questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No questions matched the selection",
        )

    new_quiz = Quiz(
        course_id=course_id,
        created_by=user.id,
        title=body.title,
        description=source.description,
        quiz_type=source.quiz_type,
        purpose="live",
        is_published=True,
    )
    db.add(new_quiz)
    await db.flush()

    for idx, q in enumerate(source_questions):
        db.add(
            Question(
                quiz_id=new_quiz.id,
                question_index=idx,
                type=q.type,
                question_text=q.question_text,
                options=q.options,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                difficulty=q.difficulty,
                source_chunk_id=q.source_chunk_id,
            )
        )

    await db.commit()
    await db.refresh(new_quiz)

    return APIResponse(
        success=True,
        data=QuizResponse(
            id=new_quiz.id,
            course_id=new_quiz.course_id,
            title=new_quiz.title,
            description=new_quiz.description,
            quiz_type=new_quiz.quiz_type,
            purpose=new_quiz.purpose,
            folder_id=new_quiz.folder_id,
            is_published=new_quiz.is_published,
            question_count=len(source_questions),
            created_at=new_quiz.created_at,
        ),
    )


# ---------------------------------------------------------------------------
# Quiz folders
# ---------------------------------------------------------------------------


async def _folder_descendant_ids(
    db: AsyncSession, root_id: uuid.UUID
) -> set[uuid.UUID]:
    """Return all descendant folder ids of root_id (inclusive)."""
    result: set[uuid.UUID] = {root_id}
    frontier = [root_id]
    while frontier:
        rows = (
            await db.execute(
                select(QuizFolder.id).where(
                    QuizFolder.parent_id.in_(frontier),
                    QuizFolder.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        frontier = [r for r in rows if r not in result]
        result.update(frontier)
    return result


@router.get(
    "/courses/{course_id}/quiz-folders",
    response_model=APIResponse[list[QuizFolderResponse]],
)
async def list_quiz_folders(
    course_id: uuid.UUID,
    purpose: Literal["after_class", "live"] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, course_id, user.id)
    stmt = (
        select(QuizFolder)
        .where(
            QuizFolder.course_id == course_id,
            QuizFolder.deleted_at.is_(None),
        )
        .order_by(QuizFolder.created_at)
    )
    if purpose is not None:
        stmt = stmt.where(QuizFolder.purpose == purpose)
    result = await db.execute(stmt)
    folders = result.scalars().all()
    return APIResponse(
        success=True,
        data=[QuizFolderResponse.model_validate(f) for f in folders],
    )


@router.post(
    "/courses/{course_id}/quiz-folders",
    response_model=APIResponse[QuizFolderResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_quiz_folder(
    course_id: uuid.UUID,
    body: QuizFolderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_enrollment(db, course_id, user.id)

    if body.parent_id is not None:
        parent = await db.get(QuizFolder, body.parent_id)
        if (
            parent is None
            or parent.deleted_at is not None
            or parent.course_id != course_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent folder not found in this course",
            )

    if body.purpose not in {"after_class", "live"}:
        raise HTTPException(status_code=400, detail="Invalid purpose")
    folder = QuizFolder(
        course_id=course_id,
        name=body.name.strip() or "Untitled",
        parent_id=body.parent_id,
        purpose=body.purpose,
        created_by=user.id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return APIResponse(
        success=True,
        data=QuizFolderResponse.model_validate(folder),
    )


@router.patch(
    "/quiz-folders/{folder_id}",
    response_model=APIResponse[QuizFolderResponse],
)
async def rename_quiz_folder(
    folder_id: uuid.UUID,
    body: QuizFolderRename,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    folder = await db.get(QuizFolder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, folder.course_id, user.id)

    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    folder.name = new_name
    await db.commit()
    await db.refresh(folder)
    return APIResponse(success=True, data=QuizFolderResponse.model_validate(folder))


@router.post(
    "/quiz-folders/{folder_id}/move",
    response_model=APIResponse[QuizFolderResponse],
)
async def move_quiz_folder(
    folder_id: uuid.UUID,
    body: QuizFolderMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    folder = await db.get(QuizFolder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, folder.course_id, user.id)

    if body.parent_id is not None:
        if body.parent_id == folder_id:
            raise HTTPException(status_code=400, detail="Cannot nest folder inside itself")
        parent = await db.get(QuizFolder, body.parent_id)
        if (
            parent is None
            or parent.deleted_at is not None
            or parent.course_id != folder.course_id
        ):
            raise HTTPException(status_code=400, detail="Parent folder not found in this course")
        descendants = await _folder_descendant_ids(db, folder_id)
        if body.parent_id in descendants:
            raise HTTPException(status_code=400, detail="Cannot move folder into its own descendant")

    folder.parent_id = body.parent_id
    await db.commit()
    await db.refresh(folder)
    return APIResponse(success=True, data=QuizFolderResponse.model_validate(folder))


@router.delete(
    "/quiz-folders/{folder_id}",
    response_model=APIResponse[None],
)
async def delete_quiz_folder(
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    folder = await db.get(QuizFolder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, folder.course_id, user.id)

    new_parent = folder.parent_id

    # Reparent child folders + quizzes to this folder's parent (may be None).
    await db.execute(
        Quiz.__table__.update()
        .where(Quiz.folder_id == folder_id)
        .values(folder_id=new_parent)
    )
    await db.execute(
        QuizFolder.__table__.update()
        .where(QuizFolder.parent_id == folder_id)
        .values(parent_id=new_parent)
    )

    folder.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.patch(
    "/quizzes/{quiz_id}/folder",
    response_model=APIResponse[QuizResponse],
)
async def move_quiz_to_folder(
    quiz_id: uuid.UUID,
    body: QuizMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None or quiz.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    await _verify_enrollment(db, quiz.course_id, user.id)

    if body.folder_id is not None:
        folder = await db.get(QuizFolder, body.folder_id)
        if (
            folder is None
            or folder.deleted_at is not None
            or folder.course_id != quiz.course_id
        ):
            raise HTTPException(status_code=400, detail="Folder not found in this course")

    quiz.folder_id = body.folder_id
    await db.commit()
    await db.refresh(quiz)

    count_stmt = select(func.count(Question.id)).where(Question.quiz_id == quiz.id)
    question_count = (await db.execute(count_stmt)).scalar_one()

    return APIResponse(
        success=True,
        data=QuizResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            purpose=quiz.purpose,
            folder_id=quiz.folder_id,
            is_published=quiz.is_published,
            question_count=question_count,
            created_at=quiz.created_at,
        ),
    )
