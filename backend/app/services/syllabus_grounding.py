"""Load the most recent applied SyllabusImport.parsed_payload for a course
and render it as a grounding-context block for generation prompts."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SyllabusImport


def _render_payload(payload: dict[str, Any]) -> str:
    """Render selected fields of parsed_payload into prompt-friendly text.

    We deliberately surface course objectives + per-meeting objectives, but
    NOT the raw schedule — generators don't need to know the time-of-day a
    meeting happens, and the larger the grounding block the more it eats the
    context budget.
    """
    parts: list[str] = []

    course = payload.get("course") or {}
    if course:
        bits: list[str] = []
        if course.get("name"):
            bits.append(f"Course: {course['name']}")
        if course.get("semester"):
            bits.append(f"Semester: {course['semester']}")
        if bits:
            parts.append(" | ".join(bits))

    objectives = payload.get("objectives") or []
    course_objs = [
        o for o in objectives if (o.get("scope") or "course") == "course"
    ]
    if course_objs:
        parts.append("Course Learning Outcomes:")
        for obj in course_objs[:20]:
            stmt = (obj.get("statement") or "").strip()
            level = obj.get("bloom_level")
            if stmt:
                parts.append(f"  - {stmt}" + (f" [{level}]" if level else ""))

    meetings = payload.get("meetings") or []
    if meetings:
        parts.append("Meeting-Level Objectives (chronological):")
        for m in meetings[:20]:
            objs = m.get("objective_statements") or []
            if not objs:
                continue
            title = m.get("title") or f"Meeting {m.get('meeting_index', '?')}"
            parts.append(f"  {title}:")
            for s in objs[:5]:
                if s and isinstance(s, str):
                    parts.append(f"    · {s}")

    return "\n".join(parts).strip()


async def load_syllabus_grounding(
    db: AsyncSession, course_id: uuid.UUID
) -> str | None:
    """Return rendered grounding text, or None if no applied syllabus exists."""
    row = (
        await db.execute(
            select(SyllabusImport)
            .where(
                SyllabusImport.course_id == course_id,
                SyllabusImport.status == "applied",
            )
            .order_by(SyllabusImport.applied_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None or not row.parsed_payload:
        return None
    rendered = _render_payload(row.parsed_payload)
    return rendered or None
