import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class QuestionResponse(BaseModel):
    id: uuid.UUID
    question_index: int
    type: str
    question_text: str
    options: dict | None
    explanation: str | None

    model_config = {"from_attributes": True}


class QuestionWithAnswerResponse(QuestionResponse):
    correct_answer: str


class QuizResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    description: str | None
    quiz_type: str
    purpose: str = "after_class"
    is_published: bool
    question_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QuizDetailResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    description: str | None
    quiz_type: str
    is_published: bool
    questions: list[QuestionResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class QuizPreviewResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    description: str | None
    quiz_type: str
    is_published: bool
    questions: list[QuestionWithAnswerResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionCreate(BaseModel):
    question_text: str
    options: dict[str, str]
    correct_answer: str
    explanation: str | None = None


class QuizUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


class QuizAttemptCreate(BaseModel):
    answers: dict[str, str]
    time_taken_seconds: int | None = None


class QuizAttemptResult(BaseModel):
    question_id: uuid.UUID
    question_text: str
    selected_answer: str
    correct_answer: str
    is_correct: bool
    explanation: str | None


class QuizAttemptResponse(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    score: Decimal
    total_questions: int
    correct_count: int
    time_taken_seconds: int | None
    results: list[QuizAttemptResult]
    completed_at: datetime | None

    model_config = {"from_attributes": True}
