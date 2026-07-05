# backend/app/schemas/decision.py
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AlertType = Literal[
    "student_disengaging", "student_falling_behind",
    "cohort_concept_weakness", "prereq_gap_for_upcoming_meeting",
    "low_quiz_participation", "missed_deadline", "content_gap",
]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["open", "dismissed", "resolved"]


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
