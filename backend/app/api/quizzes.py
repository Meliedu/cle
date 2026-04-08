import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_instructor
from app.models.course import Enrollment
from app.models.quiz import Question, Quiz, QuizAttempt
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.quiz import (
    QuestionResponse,
    QuizAttemptCreate,
    QuizAttemptResponse,
    QuizAttemptResult,
    QuizDetailResponse,
    QuizResponse,
    QuizUpdate,
)

router = APIRouter(tags=["quizzes"])


async def _verify_enrollment(
    db: AsyncSession,
    course_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
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


@router.get(
    "/courses/{course_id}/quizzes",
    response_model=APIResponse[list[QuizResponse]],
)
async def list_quizzes(
    course_id: uuid.UUID,
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

    quiz.is_published = True
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
            is_published=quiz.is_published,
            question_count=question_count,
            created_at=quiz.created_at,
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
            Quiz.is_published.is_(True),
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
