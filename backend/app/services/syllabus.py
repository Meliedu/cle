"""Syllabus parsing + apply.

`parse_syllabus_text` is a thin wrapper around an LLM structured-output call.
`apply_syllabus_payload` is the transactional applier that creates modules /
meetings / objectives / assignments from the (possibly instructor-edited)
payload.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Assignment,
    CourseMeeting,
    CourseModule,
    LearningObjective,
)

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You extract structured syllabus data from arbitrary syllabus text.
Output ONLY a JSON object matching this schema:
{
  "course": {"name": "string", "semester": "string|null", "language": "string|null"},
  "modules": [{"name": "string", "order_index": int, "description": "string|null"}],
  "meetings": [{
      "module_index": int, "meeting_index": int,
      "scheduled_at": "ISO 8601 datetime",
      "title": "string|null",
      "objective_statements": ["string"]
  }],
  "objectives": [{
      "scope": "course|module|meeting",
      "scope_index": int|null,
      "statement": "string",
      "bloom_level": "remember|understand|apply|analyze|evaluate|create|null"
  }],
  "assignments": [{
      "title": "string", "kind": "essay|project|quiz|reading|presentation|lab|problem_set|participation|other",
      "due_at": "ISO 8601 datetime", "weight": float|null,
      "module_index": int|null, "meeting_index": int|null
  }],
  "schema_version": "v1"
}
If a field is missing, omit it. Do not hallucinate dates."""


async def _llm_extract(raw_text: str) -> dict[str, Any]:
    """LLM call. Separate function so tests can monkeypatch."""
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    resp = await client.chat.completions.create(
        model=settings.llm_primary_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": raw_text[:40000]},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content or "{}")


async def parse_syllabus_text(raw_text: str) -> dict[str, Any]:
    """Extract structured payload from syllabus text via LLM."""
    payload = await _llm_extract(raw_text)
    if "schema_version" not in payload:
        payload["schema_version"] = "v1"
    return payload


async def apply_syllabus_payload(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
    payload: dict[str, Any],
    applied_by: uuid.UUID,
) -> None:
    """Idempotent-ish: dedupes modules/meetings/objectives/assignments by name+index.

    Designed to be called inside a caller-managed transaction. Caller commits.
    """
    # ---- modules: dedupe by (course_id, name) ----
    module_id_by_index: dict[int, uuid.UUID] = {}
    for raw in payload.get("modules", []):
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        oi = int(raw.get("order_index", 0))
        existing = (
            await db.execute(
                select(CourseModule).where(
                    CourseModule.course_id == course_id,
                    CourseModule.name == name,
                    CourseModule.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            mod = existing
        else:
            mod = CourseModule(
                course_id=course_id, name=name, order_index=oi,
                description=raw.get("description"),
            )
            db.add(mod)
            await db.flush()
        module_id_by_index[oi] = mod.id

    # ---- meetings: dedupe by (course_id, meeting_index) ----
    meeting_id_by_index: dict[int, uuid.UUID] = {}
    for raw in payload.get("meetings", []):
        mi = int(raw.get("meeting_index", 0))
        if mi <= 0:
            continue
        existing = (
            await db.execute(
                select(CourseMeeting).where(
                    CourseMeeting.course_id == course_id,
                    CourseMeeting.meeting_index == mi,
                    CourseMeeting.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        scheduled = datetime.fromisoformat(raw["scheduled_at"].replace("Z", "+00:00"))
        mod_idx = raw.get("module_index")
        module_id = module_id_by_index.get(int(mod_idx)) if mod_idx is not None else None
        if existing:
            existing.title = raw.get("title") or existing.title
            existing.scheduled_at = scheduled
            if module_id and existing.module_id is None:
                existing.module_id = module_id
            mt = existing
        else:
            mt = CourseMeeting(
                course_id=course_id, meeting_index=mi,
                title=raw.get("title"), scheduled_at=scheduled,
                module_id=module_id,
            )
            db.add(mt)
            await db.flush()
        meeting_id_by_index[mi] = mt.id

    # ---- objectives: dedupe by (course_id, statement) ----
    for raw in payload.get("objectives", []):
        stmt = (raw.get("statement") or "").strip()
        if not stmt:
            continue
        scope = raw.get("scope") or "course"
        scope_idx = raw.get("scope_index")
        module_id = (
            module_id_by_index.get(int(scope_idx))
            if scope == "module" and scope_idx is not None else None
        )
        meeting_id = (
            meeting_id_by_index.get(int(scope_idx))
            if scope == "meeting" and scope_idx is not None else None
        )
        existing = (
            await db.execute(
                select(LearningObjective).where(
                    LearningObjective.course_id == course_id,
                    LearningObjective.statement == stmt,
                    LearningObjective.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        obj = LearningObjective(
            course_id=course_id, statement=stmt,
            bloom_level=raw.get("bloom_level"),
            module_id=module_id, meeting_id=meeting_id,
        )
        db.add(obj)

    # ---- assignments: dedupe by (course_id, title, due_at) ----
    for raw in payload.get("assignments", []):
        title = (raw.get("title") or "").strip()
        if not title:
            continue
        due = datetime.fromisoformat(raw["due_at"].replace("Z", "+00:00"))
        existing = (
            await db.execute(
                select(Assignment).where(
                    Assignment.course_id == course_id,
                    Assignment.title == title,
                    Assignment.due_at == due,
                    Assignment.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        weight = raw.get("weight")
        weight_dec = Decimal(str(weight)) if weight is not None else None
        mod_idx = raw.get("module_index")
        mt_idx = raw.get("meeting_index")
        a = Assignment(
            course_id=course_id, title=title,
            kind=raw.get("kind", "other"),
            due_at=due, weight=weight_dec,
            module_id=module_id_by_index.get(int(mod_idx)) if mod_idx is not None else None,
            meeting_id=meeting_id_by_index.get(int(mt_idx)) if mt_idx is not None else None,
            created_by=applied_by, is_published=False,
        )
        db.add(a)
