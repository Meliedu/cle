from datetime import date

from pydantic import BaseModel


class ProgressResponse(BaseModel):
    course_id: str
    xp_points: int
    streak_days: int
    last_activity_date: date | None
    quizzes_completed: int
    flashcards_reviewed: int
    speaking_sessions: int
    badges: list[str]


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    full_name: str
    avatar_url: str | None
    xp_points: int


class XPAwardResponse(BaseModel):
    xp_earned: int
    total_xp: int
    streak_days: int
    new_badges: list[str]
