import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, model_validator


QuestionDifficulty = Literal["easy", "medium", "hard"]

# --- P5 score-policy enums (mirror the DB CHECK constraints on `quizzes`) ---
# assessment_purpose ∈ practice|graded ; grading_mode ∈ auto|manual|participation ;
# late_rule ∈ accept_late|reject_late|accept_with_flag. Used by QuizUpdate so a
# teacher can PERSIST the graded-quiz policy (previously silently dropped) and
# satisfy the B5 publish gate.
AssessmentPurpose = Literal["practice", "graded"]
GradingMode = Literal["auto", "manual", "participation"]
LateRule = Literal["accept_late", "reject_late", "accept_with_flag"]


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

    # --- P5 B6 score-bearing disclosure (Decision 5/7) ---
    # Surfaced so the student landing (S050) can show the graded-vs-practice
    # disclosure BEFORE starting: whether the attempt counts, its point value,
    # the late policy, and the deadline window. Answer keys stay redacted in
    # ``questions`` (students get ``correct_answer=None``).
    assessment_purpose: str = "practice"
    score_bearing: bool = False
    points: Decimal | None = None
    late_rule: str | None = None
    due_at: datetime | None = None
    close_at: datetime | None = None

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
    # P5 B7: free-string type (Decision 2). Defaults to multiple_choice so the
    # existing MC create path is unchanged. For the new renderers (matching,
    # ordering, short_answer) `options` may be any JSON payload and
    # `correct_answer` is a JSON-encoded key — the handler calls
    # `validate_question_shape` to reject malformed new-type payloads.
    type: str = "multiple_choice"
    options: dict | None = None
    correct_answer: str
    explanation: str | None = None

    @model_validator(mode="after")
    def _validate_correct_answer(self) -> "QuestionCreate":
        # MC-only cross-field check (UNCHANGED behavior): the answer must be an
        # option key. New types are validated in the handler via
        # `validate_question_shape` (their `correct_answer` is JSON-encoded).
        if self.type == "multiple_choice":
            if not self.options or self.correct_answer not in self.options:
                raise ValueError("correct_answer must be one of the option keys")
        return self


class QuestionUpdate(BaseModel):
    question_text: str | None = None
    # P5 B7: an explicit type change routes shape validation to the new type.
    type: str | None = None
    options: dict | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    difficulty: QuestionDifficulty | None = None

    @model_validator(mode="after")
    def _validate_correct_answer(self) -> "QuestionUpdate":
        # When both options and correct_answer are provided for an MC question
        # (no type change, or an explicit type='multiple_choice'), the answer
        # must be a key of the new options. Cross-field checks for new types /
        # partial updates are enforced in the handler where the DB row's type +
        # current options are known.
        is_mc = self.type is None or self.type == "multiple_choice"
        if (
            is_mc
            and self.options is not None
            and self.correct_answer is not None
        ):
            if self.correct_answer not in self.options:
                raise ValueError(
                    "correct_answer must be one of the option keys"
                )
        return self


class QuizUpdate(BaseModel):
    title: str | None = None
    description: str | None = None

    # --- P5 score-policy (B1 columns) ---
    # All optional so the update stays a partial patch: the handler applies only
    # the fields the client actually sent (``model_dump(exclude_unset=True)``).
    # Enums are validated here against the DB CHECK constraints so an invalid
    # value is a 422 before it ever reaches the row. Persisting these is what
    # lets a graded quiz satisfy the B5 publish gate.
    assessment_purpose: AssessmentPurpose | None = None
    score_bearing: bool | None = None
    score_category_id: uuid.UUID | None = None
    points: Decimal | None = None
    grading_mode: GradingMode | None = None
    late_rule: LateRule | None = None
    open_at: datetime | None = None
    due_at: datetime | None = None
    close_at: datetime | None = None


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
