"""Checklist / work-item schemas (P4 B6).

The checklist spine (spec §4.6) has two audiences:

* the STUDENT reads a merged view — each course work_item + the caller's own
  ``work_item_progress`` status (``ChecklistItem``); the dashboard next-action
  reads the same spine (``ChecklistItem | None``).
* the TEACHER reads/authors the raw work_items with NO per-student progress
  (``WorkItemResponse``) and mutates them via ``WorkItemCreate`` /
  ``WorkItemUpdate``.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# The full spec §4.6 source_kind enum (mirrors ``ck_work_items_source_kind_valid``).
SourceKind = Literal[
    "checkpoint", "practice", "quiz", "activity", "material", "follow_up", "report"
]

# The full spec §4.6 progress lifecycle (mirrors
# ``ck_work_item_progress_status_valid``). ``pending`` is the derived default for
# an item the caller has not yet touched.
WorkItemStatus = Literal[
    "pending", "in_progress", "submitted", "late", "missed", "completed",
    "follow_up_assigned",
]


class ChecklistItem(BaseModel):
    """One checklist row for a student: the work_item + the caller's own status.

    ``status`` is the caller's ``work_item_progress`` status when a row exists,
    else a fallback derived from ``checkpoint_responses`` (for pre-backfill
    checkpoint items, Decision 4), else ``pending``.
    """

    id: uuid.UUID
    course_id: uuid.UUID
    source_kind: SourceKind
    source_id: uuid.UUID
    title: str
    required: bool
    score_bearing: bool
    due_at: datetime | None = None
    close_at: datetime | None = None
    visible_from: datetime | None = None
    status: WorkItemStatus


class WorkItemResponse(BaseModel):
    """A raw work_item for the teacher manager (NO per-student progress)."""

    id: uuid.UUID
    course_id: uuid.UUID
    source_kind: SourceKind
    source_id: uuid.UUID
    title: str
    required: bool
    score_bearing: bool
    due_at: datetime | None = None
    close_at: datetime | None = None
    visible_from: datetime | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkItemCreate(BaseModel):
    """Body for ``POST /courses/{id}/work-items`` — a teacher manual add.

    A manual item has no backing artifact, so ``source_id`` is server-generated
    (a fresh UUID, which can never collide on the ``(course, source_kind,
    source_id)`` unique index). ``source_kind`` defaults to ``material`` — the
    only non-checkpoint source P4 writes — but any valid enum value is accepted.
    """

    title: str = Field(min_length=1, max_length=255)
    source_kind: SourceKind = "material"
    required: bool = True
    score_bearing: bool = False
    due_at: datetime | None = None
    close_at: datetime | None = None
    visible_from: datetime | None = None


class WorkItemUpdate(BaseModel):
    """Body for ``PATCH /work-items/{id}`` — reorder / required / title edits.

    All fields optional (only supplied fields are applied). There is no discrete
    ordering column on ``work_items`` — the checklist orders by ``due_at`` then
    ``visible_from``, so a "reorder" is expressed by editing those timestamps.
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    required: bool | None = None
    score_bearing: bool | None = None
    due_at: datetime | None = None
    close_at: datetime | None = None
    visible_from: datetime | None = None
