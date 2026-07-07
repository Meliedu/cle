"""Carry-forward course memory — persistence + grounding render (P7 Task B9).

Course memory is **course-bound** (spec §5.6, Decision 6): when an instructor
imports prior-term ``carry_forward`` items into a new course we copy ONLY the
reviewed instructor-authored summaries — ``relationship_summary`` /
``action_summary`` / ``outcome_summary`` / ``instructor_comment``. NO student
``user_id`` (and no source ``learning_note_id``) ever crosses terms.

Persistence choice (NO new table / migration): the imported blocks live on the
NEW course's ``courses.setup_checklist`` JSONB under the ``imported_memory`` key.
``setup_checklist`` is already a JSONB on ``Course``; the setup wizard only reads
the ``SETUP_STEP_KEYS`` flags (``api/setup.py::_state``) so an extra key is inert
there — and import-memory is deliberately NOT a publish-gate step (mirrors the P1
stub decision). ``checkpoint_generation._build_context`` reads it back via
``load_carry_forward_memory`` and threads it in as one best-effort grounding block.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.models.course import Course
from app.models.evidence import CourseRecordItem

# The ``courses.setup_checklist`` key under which imported summaries live.
IMPORTED_MEMORY_KEY = "imported_memory"

_HEADER = "Prior-term course memory (carry-forward, instructor-reviewed):"


def build_import_blocks(items: list[CourseRecordItem]) -> list[dict[str, Any]]:
    """Project accepted record items → the course-bound summary blocks.

    Copies ONLY instructor-authored fields plus source-COURSE provenance (never
    a ``user_id`` / ``learning_note_id``) so no student identity crosses terms.
    """
    return [
        {
            "source_item_id": str(item.id),
            "source_course_id": str(item.course_id),
            "relationship_summary": item.relationship_summary,
            "action_summary": item.action_summary,
            "outcome_summary": item.outcome_summary,
            "instructor_comment": item.instructor_comment,
        }
        for item in items
    ]


def _summary_line(label: str, summary: Any) -> str | None:
    if not summary:
        return None
    if isinstance(summary, dict):
        body = "; ".join(f"{k}: {v}" for k, v in summary.items() if v is not None)
    else:
        body = str(summary)
    body = body.strip()
    return f"  {label}: {body}" if body else None


def render_imported_memory(blocks: list[dict[str, Any]] | None) -> str | None:
    """Render the stored blocks into a prompt-friendly grounding block, or None."""
    if not blocks:
        return None
    lines: list[str] = [_HEADER]
    for block in blocks:
        comment = (block.get("instructor_comment") or "").strip()
        if comment:
            lines.append(f"  - {comment}")
        for label, key in (
            ("relationship", "relationship_summary"),
            ("action", "action_summary"),
            ("outcome", "outcome_summary"),
        ):
            line = _summary_line(label, block.get(key))
            if line:
                lines.append(line)
    # Only the header would mean nothing to ground on.
    return "\n".join(lines) if len(lines) > 1 else None


def merge_imported_blocks(
    course: Course, new_blocks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return a NEW ``setup_checklist`` dict with ``new_blocks`` appended.

    Immutable: builds a fresh dict/list (never mutates the existing JSONB in
    place) so SQLAlchemy's change detection fires and prior imports are kept.
    Dedupes on ``source_item_id`` so a re-import is idempotent.
    """
    checklist = dict(course.setup_checklist or {})
    existing = list(checklist.get(IMPORTED_MEMORY_KEY) or [])
    seen = {b.get("source_item_id") for b in existing}
    merged = existing + [
        b for b in new_blocks if b.get("source_item_id") not in seen
    ]
    checklist[IMPORTED_MEMORY_KEY] = merged
    return checklist


async def load_carry_forward_memory(db, course_id: uuid.UUID) -> str | None:
    """Load + render the imported carry-forward memory block for a course.

    Best-effort read for ``checkpoint_generation._build_context``: returns None
    when the course is missing or nothing was imported.
    """
    course = await db.get(Course, course_id)
    if course is None:
        return None
    blocks = (course.setup_checklist or {}).get(IMPORTED_MEMORY_KEY)
    return render_imported_memory(blocks)
