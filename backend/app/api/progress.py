import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import get_current_user, get_db
from app.models.score import StudentProgress
from app.models.user import User
from app.schemas.common import APIResponse, PaginatedResponse, PaginationMeta
from app.schemas.progress import LeaderboardEntry, ProgressResponse

router = APIRouter(tags=["progress"])


@router.get(
    "/courses/{course_id}/progress",
    response_model=APIResponse[ProgressResponse],
)
async def get_my_progress(
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ProgressResponse]:
    await verify_enrollment(db, uuid.UUID(course_id), user.id)
    stmt = select(StudentProgress).where(
        StudentProgress.user_id == user.id,
        StudentProgress.course_id == course_id,
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()

    if progress is None:
        return APIResponse(
            success=True,
            data=ProgressResponse(
                course_id=course_id,
                xp_points=0,
                streak_days=0,
                last_activity_date=None,
                quizzes_completed=0,
                flashcards_reviewed=0,
                speaking_sessions=0,
                badges=[],
            ),
        )

    return APIResponse(
        success=True,
        data=ProgressResponse(
            course_id=str(progress.course_id),
            xp_points=progress.xp_points or 0,
            streak_days=progress.streak_days or 0,
            last_activity_date=progress.last_activity_date,
            quizzes_completed=progress.quizzes_completed or 0,
            flashcards_reviewed=progress.flashcards_reviewed or 0,
            speaking_sessions=progress.speaking_sessions or 0,
            badges=progress.badges or [],
        ),
    )


@router.get(
    "/courses/{course_id}/leaderboard",
    response_model=PaginatedResponse[LeaderboardEntry],
)
async def get_leaderboard(
    course_id: str,
    page: int = 1,
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[LeaderboardEntry]:
    await verify_enrollment(db, uuid.UUID(course_id), user.id)
    count_stmt = (
        select(func.count())
        .select_from(StudentProgress)
        .where(
            StudentProgress.course_id == course_id,
            StudentProgress.xp_points > 0,
        )
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(StudentProgress, User)
        .join(User, StudentProgress.user_id == User.id)
        .where(
            StudentProgress.course_id == course_id,
            StudentProgress.xp_points > 0,
        )
        .order_by(StudentProgress.xp_points.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    entries = [
        LeaderboardEntry(
            rank=(page - 1) * limit + i + 1,
            user_id=str(prog.user_id),
            full_name=user_row.full_name or "Anonymous",
            avatar_url=user_row.avatar_url,
            xp_points=prog.xp_points or 0,
        )
        for i, (prog, user_row) in enumerate(rows)
    ]

    pages = -(-total // limit) if total > 0 else 0

    return PaginatedResponse(
        success=True,
        data=entries,
        meta=PaginationMeta(
            total=total,
            page=page,
            limit=limit,
            pages=pages,
        ),
    )
