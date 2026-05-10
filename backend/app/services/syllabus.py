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
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError
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


# --- LLM output validation schema -------------------------------------------
# The LLM occasionally hallucinates malformed values (wrong enum, oversized
# strings, payloads with hundreds of fictional assignments). Validate before
# storing parsed_payload so the apply path can rely on shapes without
# scattering ``int(...)`` / ``.get(...)`` defensiveness — and so a
# prompt-injected payload can't crash the apply transaction halfway through.

_BLOOM_VALUES = (
    "remember", "understand", "apply", "analyze", "evaluate", "create",
)
_ASSIGNMENT_KINDS = (
    "essay", "project", "quiz", "reading", "presentation", "lab",
    "problem_set", "participation", "other",
)
_OBJECTIVE_SCOPES = ("course", "module", "meeting")

# Reasonable upper bounds — a real syllabus has tens of items, not thousands.
# These cap the blast radius of a prompt-injected response.
_MAX_MODULES = 50
_MAX_MEETINGS = 200
_MAX_OBJECTIVES = 200
_MAX_ASSIGNMENTS = 200
_MAX_NAME = 255
_MAX_TEXT = 2000


class _SyllabusCourseV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., max_length=_MAX_NAME)
    semester: str | None = Field(None, max_length=_MAX_NAME)
    language: str | None = Field(None, max_length=64)


class _SyllabusModuleV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., max_length=_MAX_NAME)
    order_index: int = Field(..., ge=0, le=10_000)
    description: str | None = Field(None, max_length=_MAX_TEXT)


class _SyllabusMeetingV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    module_index: int | None = Field(None, ge=0, le=10_000)
    meeting_index: int = Field(..., ge=1, le=10_000)
    scheduled_at: str = Field(..., max_length=64)
    title: str | None = Field(None, max_length=_MAX_NAME)
    objective_statements: list[str] = Field(default_factory=list, max_length=50)


class _SyllabusObjectiveV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scope: Literal["course", "module", "meeting"] = "course"
    scope_index: int | None = Field(None, ge=0, le=10_000)
    statement: str = Field(..., max_length=_MAX_TEXT)
    bloom_level: Literal[
        "remember", "understand", "apply", "analyze", "evaluate", "create",
    ] | None = None


class _SyllabusAssignmentV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(..., max_length=_MAX_NAME)
    kind: Literal[
        "essay", "project", "quiz", "reading", "presentation", "lab",
        "problem_set", "participation", "other",
    ] = "other"
    due_at: str = Field(..., max_length=64)
    weight: float | None = Field(None, ge=0, le=1000)
    module_index: int | None = Field(None, ge=0, le=10_000)
    meeting_index: int | None = Field(None, ge=0, le=10_000)


class _SyllabusPayloadV1(BaseModel):
    """Strict Pydantic schema for LLM syllabus output.

    Field caps prevent a malformed or prompt-injected payload from
    crashing the apply transaction halfway through — datetimes are still
    parsed at apply time (the ISO format varies enough that string typing
    here keeps validation tolerant) but everything else has hard limits.
    """
    model_config = ConfigDict(extra="ignore")

    course: _SyllabusCourseV1 | None = None
    modules: list[_SyllabusModuleV1] = Field(
        default_factory=list, max_length=_MAX_MODULES
    )
    meetings: list[_SyllabusMeetingV1] = Field(
        default_factory=list, max_length=_MAX_MEETINGS
    )
    objectives: list[_SyllabusObjectiveV1] = Field(
        default_factory=list, max_length=_MAX_OBJECTIVES
    )
    assignments: list[_SyllabusAssignmentV1] = Field(
        default_factory=list, max_length=_MAX_ASSIGNMENTS
    )
    schema_version: Literal["v1"] = "v1"


class SyllabusValidationError(ValueError):
    """Raised when LLM output fails strict-schema validation. Callers map
    this to a ``failed`` import status with the error stored on the row."""


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
    # Fix 12: warn when the syllabus text is truncated before sending to LLM
    content = raw_text[:40000]
    if len(raw_text) > 40000:
        logger.warning(
            "Syllabus text truncated for LLM: original=%d chars, sent=%d chars",
            len(raw_text),
            40000,
        )
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    resp = await client.chat.completions.create(
        model=settings.llm_primary_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content or "{}")


async def parse_syllabus_text(raw_text: str) -> dict[str, Any]:
    """Extract a strict-validated structured payload from syllabus text.

    Raises :class:`SyllabusValidationError` if the LLM returns malformed
    JSON, oversize strings, unknown enum values, or hundreds of items —
    typical hallucination/prompt-injection symptoms. The caller (the
    parse_syllabus task) maps this to a ``failed`` import status so the
    UI can surface the issue and the apply path never sees junk.

    The dict round-trip via ``model_dump`` ensures field caps and enum
    constraints are baked in before storage.
    """
    payload = await _llm_extract(raw_text)
    if "schema_version" not in payload:
        payload["schema_version"] = "v1"
    try:
        validated = _SyllabusPayloadV1.model_validate(payload)
    except ValidationError as exc:
        # Surface a concise summary; the full pydantic error tree is too
        # noisy for tasks.error_message and would also leak internals.
        first = exc.errors()[0] if exc.errors() else {"msg": "validation failed"}
        loc = ".".join(str(p) for p in first.get("loc", ())) or "<root>"
        raise SyllabusValidationError(
            f"LLM payload failed validation at {loc}: {first.get('msg', 'invalid')}"
        ) from exc
    return validated.model_dump(mode="json", exclude_none=False)


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
        # Fix 6: guard against missing/malformed scheduled_at
        scheduled_raw = raw.get("scheduled_at")
        if not scheduled_raw or not isinstance(scheduled_raw, str):
            logger.warning("Skipping meeting %d with invalid scheduled_at", mi)
            continue
        try:
            scheduled = datetime.fromisoformat(scheduled_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
            logger.warning("Skipping meeting %d with malformed scheduled_at: %s", mi, exc)
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
        # Fix 6: guard against missing/malformed due_at
        due_raw = raw.get("due_at")
        if not due_raw or not isinstance(due_raw, str):
            logger.warning("Skipping assignment '%s' with invalid due_at", title)
            continue
        try:
            due = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
            logger.warning("Skipping assignment '%s' with malformed due_at: %s", title, exc)
            continue
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
