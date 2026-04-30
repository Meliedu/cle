# backend/app/schemas/decision.py
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

ActionType = Literal[
    "review_concept", "prep_meeting", "complete_assignment",
    "do_quiz", "practice_weakness", "catch_up_reading",
    "flashcard_review", "pronunciation_practice", "watch_recording",
]
NextActionTargetKind = Literal[
    "concept", "course_meeting", "assignment", "quiz",
    "flashcard_set", "pronunciation_set", "document", "chunk",
]
CandidateSource = Literal["outer_fringe", "deadline", "review", "fallback"]
EngineMode = Literal["on", "off", "random_50"]
OverrideMode = Literal["on", "off"]
AlertType = Literal[
    "student_disengaging", "student_falling_behind",
    "cohort_concept_weakness", "prereq_gap_for_upcoming_meeting",
    "low_quiz_participation", "missed_deadline", "content_gap",
]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["open", "dismissed", "resolved"]
OutcomeMetric = Literal["mastery_delta", "quiz_score", "recall", "completion"]


class NextActionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    course_id: uuid.UUID | None
    action_type: ActionType
    target_kind: NextActionTargetKind | None
    target_id: uuid.UUID | None
    # Pydantic v2 serialises Decimal to a JSON string (not a number); frontend
    # consumers must parseFloat() before doing numeric operations or sorting.
    priority_score: Decimal
    candidate_source: CandidateSource
    reason: dict
    expires_at: datetime
    served_at: datetime | None
    clicked_at: datetime | None
    consumed_at: datetime | None
    engine_variant: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NextActionClickResponse(BaseModel):
    id: uuid.UUID
    clicked_at: datetime
    target_kind: NextActionTargetKind | None
    target_id: uuid.UUID | None


class EngineSettingsResponse(BaseModel):
    course_id: uuid.UUID
    mode: EngineMode
    overrides_count: int


class EngineSettingsUpdate(BaseModel):
    mode: EngineMode


class EngineOverrideUpdate(BaseModel):
    mode: OverrideMode


class EngineOverrideResponse(BaseModel):
    user_id: uuid.UUID
    course_id: uuid.UUID
    mode: OverrideMode
    set_by: uuid.UUID
    set_at: datetime

    model_config = {"from_attributes": True}


class InstructorAlertResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    instructor_id: uuid.UUID
    target_user_id: uuid.UUID | None
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    reason: dict
    status: AlertStatus
    resolved_at: datetime | None
    resolved_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InstructorAlertUpdate(BaseModel):
    status: Literal["dismissed", "resolved"]
