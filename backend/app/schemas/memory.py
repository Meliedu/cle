"""Course-memory schemas (P7 Task B8).

Request/response models for the teacher course-memory surface over
``course_record_items`` (spec §4.10, Decision 5). ``MemoryItemResponse`` serves
BOTH the list and the detail read (same shape); ``kind`` is a derived label
computed from which summary JSONBs are populated (it is NOT a stored column).
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# The instructor decision enum (Decision 5). ``reject`` is an audited tombstone
# (no hard delete); ``carry_forward`` also flips the ``carry_forward`` bool.
MemoryDecision = Literal["keep", "revise", "reject", "carry_forward"]

# Derived label — priority: outcome > action > relationship > general.
MemoryKind = Literal["outcome", "action", "relationship", "general"]


class MemoryItemResponse(BaseModel):
    """One ``course_record_items`` row (list item + detail).

    ``kind`` is derived (not stored) from which summary JSONBs are populated so
    the frontend can group by memory type. ``decision`` is NULL until an
    instructor decides; ``carry_forward`` is kept in sync (true iff decision is
    ``carry_forward``).
    """

    id: uuid.UUID
    course_id: uuid.UUID
    learning_note_id: uuid.UUID | None
    kind: MemoryKind
    relationship_summary: dict | None
    action_summary: dict | None
    outcome_summary: dict | None
    instructor_comment: str | None
    carry_forward: bool
    decision: MemoryDecision | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    report_history: list
    created_at: datetime


class MemoryDecideRequest(BaseModel):
    """Teacher decision on a memory item (Decision 5).

    An out-of-enum value is rejected by FastAPI with 422 before the handler runs.
    """

    decision: MemoryDecision

    model_config = {"extra": "forbid"}
