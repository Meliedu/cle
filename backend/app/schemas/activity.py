"""Activity builder schemas (P5 B8).

Request/response shapes for the teacher activity builder CRUD + publish
(``api/activities.py``). ``config`` is a free ``dict`` at the schema layer; the
router shape-validates it per ``format`` (swipe → ``prompts``, vote → ``options``,
comment_reaction → ``reactions``) and raises the typed ``ACTIVITY_CONFIG_INVALID``
so the FE (F4) can render a designed field-level error.

The read schema is ``ActivityRead`` — NOT ``ActivityResponse`` — because the ORM
already binds ``ActivityResponse`` to the student-submission table
(``models/activity.py``).
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ActivityFormat = Literal["swipe", "vote", "comment_reaction"]
GradingMode = Literal["auto", "manual", "participation"]
LateRule = Literal["accept_late", "reject_late", "accept_with_flag"]


class ActivityCreate(BaseModel):
    """Create a course-scoped activity (starts in ``draft``)."""

    format: ActivityFormat
    title: str = Field(min_length=1, max_length=255)
    config: dict | None = None
    meeting_id: uuid.UUID | None = None
    open_at: datetime | None = None
    due_at: datetime | None = None
    close_at: datetime | None = None
    anonymous: bool = False
    # §4.5 publish-settings (nullable until the teacher fills the score panel).
    score_category_id: uuid.UUID | None = None
    points: Decimal | None = None
    grading_mode: GradingMode | None = None
    late_rule: LateRule | None = None
    score_bearing: bool = False


class ActivityUpdate(BaseModel):
    """Partial edit of a draft activity. All fields optional (``exclude_unset``)."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    config: dict | None = None
    meeting_id: uuid.UUID | None = None
    open_at: datetime | None = None
    due_at: datetime | None = None
    close_at: datetime | None = None
    anonymous: bool | None = None
    score_category_id: uuid.UUID | None = None
    points: Decimal | None = None
    grading_mode: GradingMode | None = None
    late_rule: LateRule | None = None
    score_bearing: bool | None = None


class ActivityRead(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    meeting_id: uuid.UUID | None
    format: str
    title: str
    config: dict | None
    status: str
    open_at: datetime | None
    due_at: datetime | None
    close_at: datetime | None
    anonymous: bool
    score_category_id: uuid.UUID | None
    points: Decimal | None
    grading_mode: str | None
    late_rule: str | None
    score_bearing: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActivityResponseSubmit(BaseModel):
    """A student submission to one activity (B9).

    ``payload`` is a free, format-specific dict — the service interprets it per
    ``format`` (swipe: which prompt + L/R; vote: chosen option; comment_reaction:
    a reaction/comment object that STACKS inside the stored payload).
    """

    payload: dict


class ActivityResponseResult(BaseModel):
    """One persisted student submission row (result / evidence view)."""

    id: uuid.UUID
    activity_id: uuid.UUID
    user_id: uuid.UUID
    payload: dict | None
    status: str
    submitted_at: datetime

    model_config = {"from_attributes": True}


class ActivityResults(BaseModel):
    """Teacher evidence/aggregate view for one activity (B9, owner-guarded).

    ``submission_count`` is the number of student submissions; ``responses`` is
    the per-student evidence. A richer format-specific live ``distribution`` is
    computed by the B10 monitor (``compute_activity_monitor_state``).
    """

    activity_id: uuid.UUID
    format: str
    status: str
    submission_count: int
    responses: list[ActivityResponseResult]
