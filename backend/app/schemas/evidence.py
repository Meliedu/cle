# backend/app/schemas/evidence.py
"""Pydantic v2 contracts for the Meli reviewed-evidence loop.

These response/request shapes mirror ``app/models/evidence.py`` (and the
review-gated ConceptTag / InstructorAlert reframings) field-for-field so the
Phase 5 instructor-review API can serialize them directly. Enum fields use
``Literal`` types matching the DB CHECK constraints.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Enums (mirror model CHECK constraints)
# ---------------------------------------------------------------------------
EventStage = Literal[
    "entry", "before_class", "during_class", "after_class", "review"
]
VisibilityScope = Literal["student", "instructor", "course_team"]
NoteReviewStatus = Literal[
    "draft", "queued", "reviewed", "edited", "merged", "split", "archived"
]
ReviewActionType = Literal[
    "accept", "edit", "merge", "split",
    "assign_followup", "archive", "carry_forward", "mark_resolved",
]
AssignmentStatus = Literal[
    "suggested", "assigned", "viewed", "completed",
    "checked", "closed", "carried_forward",
]
OutcomeStatus = Literal[
    "pending", "completed", "improved", "persistent",
    "resolved", "needs_review", "carried_forward",
]


# ---------------------------------------------------------------------------
# Learning Event (OBJ-03)
# ---------------------------------------------------------------------------
class LearningEventResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID
    source_kind: str
    source_id: uuid.UUID | None
    stage: EventStage
    event_type: str
    value: dict
    visibility_scope: VisibilityScope
    occurred_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Learning Note (OBJ-04)
# ---------------------------------------------------------------------------
class LearningNoteResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID | None
    source_event_ids: list
    context_anchor: dict | None
    evidence_category: str | None
    observed_signal: str
    draft_interpretation: str | None
    limitation_note: str | None
    suggested_follow_up: dict | None
    review_status: NoteReviewStatus
    outcome_status: OutcomeStatus | None
    report_eligibility: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Review Action (OBJ-06)
# ---------------------------------------------------------------------------
class ReviewActionResponse(BaseModel):
    id: uuid.UUID
    learning_note_id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewer_role: str
    action_type: ReviewActionType
    prior_status: str | None
    new_status: str | None
    edit_text: str | None
    report_eligibility_change: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowUpSpec(BaseModel):
    """Inline follow-up to create as part of a review action."""

    action_type: str
    target_kind: str | None = None
    target_id: uuid.UUID | None = None
    due_at: datetime | None = None
    user_id: uuid.UUID | None = None


class ReviewActionCreate(BaseModel):
    action_type: ReviewActionType
    edit_text: str | None = None
    report_eligibility: bool | None = None
    follow_up: FollowUpSpec | None = None


# ---------------------------------------------------------------------------
# Follow-up Action (OBJ-07)
# ---------------------------------------------------------------------------
class FollowUpActionResponse(BaseModel):
    id: uuid.UUID
    learning_note_id: uuid.UUID | None
    course_id: uuid.UUID
    user_id: uuid.UUID
    action_type: str
    target_kind: str | None
    target_id: uuid.UUID | None
    assignment_status: AssignmentStatus
    due_at: datetime | None
    assigned_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowUpActionCreate(BaseModel):
    user_id: uuid.UUID
    action_type: str
    learning_note_id: uuid.UUID | None = None
    target_kind: str | None = None
    target_id: uuid.UUID | None = None
    due_at: datetime | None = None


# ---------------------------------------------------------------------------
# Outcome Check (OBJ-08)
# ---------------------------------------------------------------------------
class OutcomeCheckResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID
    learning_note_id: uuid.UUID | None
    follow_up_action_id: uuid.UUID | None
    source_event_id: uuid.UUID | None
    status: OutcomeStatus
    observed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Course Record Item (OBJ-09)
# ---------------------------------------------------------------------------
class CourseRecordItemResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    learning_note_id: uuid.UUID | None
    relationship_summary: dict | None
    action_summary: dict | None
    outcome_summary: dict | None
    instructor_comment: str | None
    carry_forward: bool
    report_history: list
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Review Queue (Review Case row + optional linked draft note)
# ---------------------------------------------------------------------------
class ReviewQueueItem(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    instructor_id: uuid.UUID
    target_user_id: uuid.UUID | None
    alert_type: str
    severity: str
    title: str
    reason: dict
    status: str
    linked_note_id: uuid.UUID | None
    linked_follow_up_id: uuid.UUID | None
    report_eligibility: bool
    resolved_at: datetime | None
    resolved_by: uuid.UUID | None
    created_at: datetime
    linked_note: LearningNoteResponse | None = None

    model_config = {"from_attributes": True}
