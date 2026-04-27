import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, model_validator


QuestionDifficulty = Literal["easy", "medium", "hard"]


class QuestionResponse(BaseModel):
    id: uuid.UUID
    question_index: int
    type: str
    question_text: str
    options: dict | None
    explanation: str | None
    difficulty: str = "medium"
    # Populated only for instructors / quiz creators on endpoints that return
    # a full quiz detail. Students always see None.
    correct_answer: str | None = None

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
    folder_id: uuid.UUID | None = None
    is_published: bool
    question_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QuizFolderResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    purpose: str = "live"
    created_at: datetime

    model_config = {"from_attributes": True}


class QuizFolderCreate(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None
    purpose: str = "live"


class QuizFolderRename(BaseModel):
    name: str


class QuizFolderMove(BaseModel):
    parent_id: uuid.UUID | None = None


class QuizMove(BaseModel):
    folder_id: uuid.UUID | None = None


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

    @model_validator(mode="after")
    def _validate_correct_answer(self) -> "QuestionCreate":
        if self.correct_answer not in self.options:
            raise ValueError("correct_answer must be one of the option keys")
        return self


class QuestionUpdate(BaseModel):
    question_text: str | None = None
    options: dict[str, str] | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    difficulty: QuestionDifficulty | None = None

    @model_validator(mode="after")
    def _validate_correct_answer(self) -> "QuestionUpdate":
        # When both options and correct_answer are provided, the answer must
        # be a key of the new options. The cross-field check on partial
        # updates (e.g. only correct_answer) is enforced in the handler since
        # we need the current options from the DB.
        if self.options is not None and self.correct_answer is not None:
            if self.correct_answer not in self.options:
                raise ValueError(
                    "correct_answer must be one of the option keys"
                )
        return self


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
