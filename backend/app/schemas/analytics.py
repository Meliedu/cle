import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class CourseOverview(BaseModel):
    total_students: int
    avg_quiz_score: Decimal | None
    total_quiz_attempts: int
    active_students_7d: int


class QuizStats(BaseModel):
    quiz_id: uuid.UUID
    title: str
    avg_score: Decimal | None
    attempt_count: int
    is_published: bool


class StudentStats(BaseModel):
    user_id: uuid.UUID
    full_name: str | None
    xp_points: int
    quizzes_completed: int
    avg_quiz_score: Decimal | None
    flashcards_reviewed: int
    last_activity_date: date | None
