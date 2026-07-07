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


class NextTermSuggestionResponse(MemoryItemResponse):
    """A ``carry_forward`` record item from a PRIOR-term course of the same
    course-code lineage (T023 / Decision 6).

    Extends ``MemoryItemResponse`` with the source-course provenance the setup
    picker needs. Matched on ``courses.code`` + the SAME ``instructor_id`` — NEVER
    on student identity; the item itself carries only instructor-authored
    summaries (no student ``user_id``).
    """

    source_course_id: uuid.UUID
    source_course_code: str | None
    source_course_name: str


class ImportMemoryRequest(BaseModel):
    """Accept a set of prior-term ``carry_forward`` items into the new course.

    Each id must resolve to an item the caller owns whose ``decision`` is
    ``carry_forward`` — an undecided / ``reject`` / ``keep`` item is refused with
    a typed 409 ``MEMORY_UNDECIDED`` (Decision 6). Empty lists are a no-op.
    """

    item_ids: list[uuid.UUID]

    model_config = {"extra": "forbid"}


class ImportMemoryResponse(BaseModel):
    """Result of a successful ``import-memory`` — the count + ids threaded into
    the new course's checkpoint-generation grounding context."""

    imported_count: int
    imported_item_ids: list[uuid.UUID]


class MemoryDecisionCounts(BaseModel):
    """Counts-by-decision for the teacher overview (T036). ``undecided`` counts
    rows whose ``decision`` is still NULL."""

    keep: int = 0
    revise: int = 0
    reject: int = 0
    carry_forward: int = 0
    undecided: int = 0


class MemorySummaryResponse(BaseModel):
    """Teacher course-overview memory summary (T036): counts-by-decision, total,
    and the carry-forward roster (the items destined for next-term import)."""

    total: int
    counts: MemoryDecisionCounts
    carry_forward_roster: list[MemoryItemResponse]
