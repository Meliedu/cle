import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

# ----- Modules -----

class CourseModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    parent_id: uuid.UUID | None = None
    order_index: int = Field(ge=0)


class CourseModuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_id: uuid.UUID | None = None
    order_index: int | None = None


class CourseModuleResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    description: str | None
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Meetings -----

MeetingStatus = Literal["planned", "in_progress", "taught", "cancelled"]


class CourseMeetingCreate(BaseModel):
    meeting_index: int = Field(ge=1)
    title: str | None = None
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=1, le=600)
    location: str | None = None
    module_id: uuid.UUID | None = None


class CourseMeetingUpdate(BaseModel):
    meeting_index: int | None = None
    title: str | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    location: str | None = None
    module_id: uuid.UUID | None = None
    status: MeetingStatus | None = None


class CourseMeetingResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    module_id: uuid.UUID | None
    meeting_index: int
    title: str | None
    scheduled_at: datetime
    duration_minutes: int
    location: str | None
    status: MeetingStatus
    canvas_event_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Objectives -----

BloomLevel = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]


class LearningObjectiveCreate(BaseModel):
    statement: str = Field(min_length=1)
    bloom_level: BloomLevel | None = None
    order_index: int = Field(default=0, ge=0)
    module_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None


class LearningObjectiveUpdate(BaseModel):
    statement: str | None = None
    bloom_level: BloomLevel | None = None
    order_index: int | None = None
    module_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None


class LearningObjectiveResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    module_id: uuid.UUID | None
    meeting_id: uuid.UUID | None
    statement: str
    bloom_level: BloomLevel | None
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Assignments -----

AssignmentKind = Literal[
    "essay", "project", "quiz", "reading", "presentation",
    "lab", "problem_set", "participation", "other",
]


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    kind: AssignmentKind
    due_at: datetime
    available_from: datetime | None = None
    weight: Decimal | None = Field(default=None, ge=0, le=999.99)
    quiz_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None
    is_published: bool = False


class AssignmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    kind: AssignmentKind | None = None
    due_at: datetime | None = None
    available_from: datetime | None = None
    weight: Decimal | None = None
    quiz_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None
    is_published: bool | None = None


class AssignmentResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    module_id: uuid.UUID | None
    meeting_id: uuid.UUID | None
    title: str
    description: str | None
    kind: AssignmentKind
    due_at: datetime
    available_from: datetime | None
    weight: Decimal | None
    quiz_id: uuid.UUID | None
    is_published: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Submissions -----

SubmissionStatus = Literal[
    "not_started", "in_progress", "submitted", "late", "graded", "excused"
]


class SubmissionUpsert(BaseModel):
    """Student-side: create-or-update own submission."""
    status: Literal["in_progress", "submitted"]
    submission_payload: dict[str, Any] | None = None


class SubmissionGrade(BaseModel):
    """Instructor-side: grade an existing submission."""
    score: Decimal = Field(ge=0)
    feedback: str | None = None
    status: Literal["graded", "excused"] = "graded"


class AssignmentSubmissionResponse(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    status: SubmissionStatus
    submitted_at: datetime | None
    score: Decimal | None
    feedback: str | None
    submission_payload: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Syllabus -----

SyllabusImportStatus = Literal["pending", "parsed", "applied", "failed", "superseded"]


class SyllabusImportResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    document_id: uuid.UUID | None
    parsed_payload: dict[str, Any]
    status: SyllabusImportStatus
    error_message: str | None
    applied_at: datetime | None
    applied_by: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SyllabusImportTriggerRequest(BaseModel):
    document_id: uuid.UUID


class SyllabusImportApplyRequest(BaseModel):
    """Body is the (possibly instructor-edited) parsed_payload to apply."""
    parsed_payload: dict[str, Any]
