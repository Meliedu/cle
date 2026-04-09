import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.score import StudentProgress

BADGE_DEFINITIONS = {
    "first_quiz": lambda p, **kw: p.quizzes_completed >= 1,
    "perfect_score": lambda p, **kw: kw.get("quiz_score") == 100.0,
    "streak_7": lambda p, **kw: p.streak_days >= 7,
    "streak_30": lambda p, **kw: p.streak_days >= 30,
    "flashcard_master": lambda p, **kw: p.flashcards_reviewed >= 100,
    "speed_learner": lambda p, **kw: (
        (kw.get("quiz_score") or 0) >= 80.0
        and kw.get("quiz_time_seconds") is not None
        and kw.get("quiz_time_seconds") < 60
    ),
}


def calculate_quiz_xp(score: float) -> int:
    """Calculate XP earned from a quiz based on the score (0-100)."""
    return int(score * 10)


def calculate_streak(
    current_streak: int,
    last_activity_date: date | None,
    today: date,
) -> tuple[int, date]:
    """Calculate updated streak given the last activity date and today's date.

    Returns (new_streak, new_last_activity_date).
    """
    if last_activity_date is None:
        return 1, today
    if last_activity_date == today:
        return current_streak, today
    if last_activity_date == today - timedelta(days=1):
        return current_streak + 1, today
    return 1, today


def check_badges(
    progress: StudentProgress,
    quiz_score: float | None = None,
    quiz_time_seconds: int | None = None,
) -> list[str]:
    """Check which new badges the student has earned.

    Returns a list of newly earned badge IDs (excludes already-held badges).
    """
    existing = set(progress.badges or [])
    new_badges: list[str] = []
    for badge_id, check_fn in BADGE_DEFINITIONS.items():
        if badge_id not in existing and check_fn(
            progress, quiz_score=quiz_score, quiz_time_seconds=quiz_time_seconds
        ):
            new_badges.append(badge_id)
    return new_badges


async def get_or_create_progress(
    db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID
) -> StudentProgress:
    """Fetch existing StudentProgress or create a new row."""
    stmt = select(StudentProgress).where(
        StudentProgress.user_id == user_id,
        StudentProgress.course_id == course_id,
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = StudentProgress(user_id=user_id, course_id=course_id)
        db.add(progress)
        await db.flush()
    return progress


async def award_xp(
    db: AsyncSession,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    xp: int,
    activity: str,
    quiz_score: float | None = None,
    quiz_time_seconds: int | None = None,
) -> dict:
    """Award XP, update streak, check badges. Returns summary."""
    progress = await get_or_create_progress(db, user_id, course_id)

    # XP
    progress.xp_points = (progress.xp_points or 0) + xp

    # Activity counters
    if activity == "quiz":
        progress.quizzes_completed = (progress.quizzes_completed or 0) + 1
    elif activity == "flashcard":
        progress.flashcards_reviewed = (progress.flashcards_reviewed or 0) + 1
    elif activity == "pronunciation":
        progress.speaking_sessions = (progress.speaking_sessions or 0) + 1

    # Streak
    today = date.today()
    new_streak, new_date = calculate_streak(
        progress.streak_days or 0, progress.last_activity_date, today
    )
    progress.streak_days = new_streak
    progress.last_activity_date = new_date

    # Badges
    new_badges = check_badges(
        progress, quiz_score=quiz_score, quiz_time_seconds=quiz_time_seconds
    )
    if new_badges:
        progress.badges = list(set((progress.badges or []) + new_badges))

    await db.flush()
    return {
        "xp_earned": xp,
        "total_xp": progress.xp_points,
        "streak_days": progress.streak_days,
        "new_badges": new_badges,
    }
