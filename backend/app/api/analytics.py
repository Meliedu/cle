import uuid
from datetime import date, timedelta, timezone, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models.course import Enrollment
from app.models.quiz import Quiz, QuizAttempt
from app.models.score import StudentProgress
from app.models.user import User
from app.schemas.analytics import CourseOverview, QuizStats, StudentStats
from app.schemas.common import APIResponse

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _verify_instructor_enrollment(
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
    "/courses/{course_id}/overview",
    response_model=APIResponse[CourseOverview],
)
async def get_course_overview(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_instructor_enrollment(db, course_id, user.id)

    # Total enrolled students
    student_count_result = await db.execute(
        select(func.count(Enrollment.user_id)).where(
            Enrollment.course_id == course_id,
            Enrollment.role == "student",
        )
    )
    total_students = student_count_result.scalar_one()

    # Quiz attempt stats for this course's quizzes
    quiz_ids_stmt = select(Quiz.id).where(
        Quiz.course_id == course_id,
        Quiz.deleted_at.is_(None),
    )

    avg_score_result = await db.execute(
        select(func.avg(QuizAttempt.score)).where(
            QuizAttempt.quiz_id.in_(quiz_ids_stmt)
        )
    )
    avg_quiz_score = avg_score_result.scalar_one()
    if avg_quiz_score is not None:
        avg_quiz_score = Decimal(str(round(float(avg_quiz_score), 2)))

    total_attempts_result = await db.execute(
        select(func.count(QuizAttempt.id)).where(
            QuizAttempt.quiz_id.in_(quiz_ids_stmt)
        )
    )
    total_quiz_attempts = total_attempts_result.scalar_one()

    # Active students in last 7 days
    cutoff = date.today() - timedelta(days=7)
    active_result = await db.execute(
        select(func.count(StudentProgress.user_id)).where(
            StudentProgress.course_id == course_id,
            StudentProgress.last_activity_date >= cutoff,
        )
    )
    active_students_7d = active_result.scalar_one()

    return APIResponse(
        success=True,
        data=CourseOverview(
            total_students=total_students,
            avg_quiz_score=avg_quiz_score,
            total_quiz_attempts=total_quiz_attempts,
            active_students_7d=active_students_7d,
        ),
    )


@router.get(
    "/courses/{course_id}/quizzes",
    response_model=APIResponse[list[QuizStats]],
)
async def get_quiz_stats(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_instructor_enrollment(db, course_id, user.id)

    stmt = (
        select(
            Quiz.id,
            Quiz.title,
            Quiz.is_published,
            func.avg(QuizAttempt.score).label("avg_score"),
            func.count(QuizAttempt.id).label("attempt_count"),
        )
        .outerjoin(QuizAttempt, QuizAttempt.quiz_id == Quiz.id)
        .where(
            Quiz.course_id == course_id,
            Quiz.deleted_at.is_(None),
        )
        .group_by(Quiz.id)
        .order_by(Quiz.created_at.desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    data = [
        QuizStats(
            quiz_id=row.id,
            title=row.title,
            is_published=row.is_published,
            avg_score=Decimal(str(round(float(row.avg_score), 2))) if row.avg_score else None,
            attempt_count=row.attempt_count,
        )
        for row in rows
    ]

    return APIResponse(success=True, data=data)


@router.get(
    "/courses/{course_id}/students",
    response_model=APIResponse[list[StudentStats]],
)
async def get_student_stats(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_instructor_enrollment(db, course_id, user.id)

    # Get all enrolled students with their progress
    stmt = (
        select(
            User.id,
            User.full_name,
            User.email,
            func.coalesce(StudentProgress.xp_points, 0).label("xp_points"),
            func.coalesce(StudentProgress.quizzes_completed, 0).label("quizzes_completed"),
            func.coalesce(StudentProgress.flashcards_reviewed, 0).label("flashcards_reviewed"),
            StudentProgress.last_activity_date,
        )
        .join(Enrollment, Enrollment.user_id == User.id)
        .outerjoin(
            StudentProgress,
            (StudentProgress.user_id == User.id)
            & (StudentProgress.course_id == course_id),
        )
        .where(
            Enrollment.course_id == course_id,
            Enrollment.role == "student",
        )
        .order_by(func.coalesce(StudentProgress.xp_points, 0).desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    # Get per-student avg quiz score
    quiz_ids_stmt = select(Quiz.id).where(
        Quiz.course_id == course_id,
        Quiz.deleted_at.is_(None),
    )

    data = []
    for row in rows:
        avg_result = await db.execute(
            select(func.avg(QuizAttempt.score)).where(
                QuizAttempt.user_id == row.id,
                QuizAttempt.quiz_id.in_(quiz_ids_stmt),
            )
        )
        avg_score = avg_result.scalar_one()

        data.append(
            StudentStats(
                user_id=row.id,
                full_name=row.full_name,
                email=row.email,
                xp_points=row.xp_points,
                quizzes_completed=row.quizzes_completed,
                avg_quiz_score=Decimal(str(round(float(avg_score), 2))) if avg_score else None,
                flashcards_reviewed=row.flashcards_reviewed,
                last_activity_date=row.last_activity_date,
            )
        )

    return APIResponse(success=True, data=data)
