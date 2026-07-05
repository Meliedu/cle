import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    CourseMeeting,
    CourseModule,
    LearningObjective,
    SyllabusImport,
)
from app.models.course import Course
from app.services.syllabus import (
    SyllabusValidationError,
    apply_syllabus_payload,
    parse_syllabus_text,
)


@pytest.mark.asyncio
async def test_parse_syllabus_text_returns_payload(monkeypatch):
    fake = {
        "course": {"name": "T", "semester": "Fall 2026", "language": "english"},
        "modules": [{"name": "Week 1", "order_index": 1}],
        "meetings": [
            {
                "module_index": 1,
                "meeting_index": 1,
                "scheduled_at": "2026-09-01T10:00:00Z",
                "title": "Intro",
                "objective_statements": [],
            },
        ],
        "objectives": [
            {
                "scope": "course",
                "statement": "Identify cost types",
                "bloom_level": "understand",
            },
        ],
        "assignments": [],
        "schema_version": "v1",
    }

    async def fake_llm(text: str) -> dict:
        return fake

    monkeypatch.setattr("app.services.syllabus._llm_extract", fake_llm)
    payload = await parse_syllabus_text("Course X. Week 1: Intro...")
    assert payload["schema_version"] == "v1"
    assert len(payload["modules"]) == 1


@pytest.mark.asyncio
async def test_parse_syllabus_text_rejects_unknown_bloom_level(monkeypatch):
    """Out-of-enum values must fail strict validation rather than reach
    the database."""
    bad = {
        "modules": [],
        "meetings": [],
        "objectives": [
            {
                "scope": "course",
                "statement": "Do thing",
                "bloom_level": "transcend",  # not a valid enum value
            }
        ],
        "assignments": [],
    }

    async def fake_llm(text: str) -> dict:
        return bad

    monkeypatch.setattr("app.services.syllabus._llm_extract", fake_llm)
    with pytest.raises(SyllabusValidationError):
        await parse_syllabus_text("anything")


@pytest.mark.asyncio
async def test_parse_syllabus_text_rejects_oversized_lists(monkeypatch):
    """A prompt-injected payload with hundreds of fictional assignments
    must be capped at validation, not persisted as-is."""
    bad = {
        "modules": [],
        "meetings": [],
        "objectives": [],
        "assignments": [
            {
                "title": f"Junk {i}",
                "kind": "essay",
                "due_at": "2026-09-01T10:00:00Z",
            }
            for i in range(500)
        ],
    }

    async def fake_llm(text: str) -> dict:
        return bad

    monkeypatch.setattr("app.services.syllabus._llm_extract", fake_llm)
    with pytest.raises(SyllabusValidationError):
        await parse_syllabus_text("anything")


@pytest.mark.asyncio
async def test_parse_syllabus_text_rejects_oversize_string(monkeypatch):
    """Strings beyond column-safe lengths must be rejected so apply can't
    fail mid-transaction with a string-too-long DB error."""
    bad = {
        "modules": [{"name": "A" * 5_000, "order_index": 1}],
        "meetings": [],
        "objectives": [],
        "assignments": [],
    }

    async def fake_llm(text: str) -> dict:
        return bad

    monkeypatch.setattr("app.services.syllabus._llm_extract", fake_llm)
    with pytest.raises(SyllabusValidationError):
        await parse_syllabus_text("anything")


@pytest.mark.asyncio
async def test_apply_syllabus_payload_creates_entities(
    db_session: AsyncSession,
    test_instructor,
):
    course = Course(
        name="T",
        language="english",
        instructor_id=test_instructor.id,
        enroll_code="SYLCRSE1",
    )
    db_session.add(course)
    await db_session.flush()

    payload = {
        "course": {"name": "T"},
        "modules": [{"name": "Week 1", "order_index": 1}],
        "meetings": [
            {
                "module_index": 1,
                "meeting_index": 1,
                "scheduled_at": "2026-09-01T10:00:00Z",
                "title": "Intro",
                "objective_statements": [],
            },
        ],
        "objectives": [
            {"scope": "course", "statement": "X", "bloom_level": "apply"},
        ],
        "assignments": [
            {
                "title": "Essay",
                "kind": "essay",
                "due_at": "2026-10-15T23:59:00Z",
                "weight": 15.0,
            },
        ],
        "schema_version": "v1",
    }

    await apply_syllabus_payload(
        db_session,
        course_id=course.id,
        payload=payload,
        applied_by=test_instructor.id,
    )
    await db_session.commit()

    modules = (
        await db_session.execute(
            select(CourseModule).where(CourseModule.course_id == course.id)
        )
    ).scalars().all()
    meetings = (
        await db_session.execute(
            select(CourseMeeting).where(CourseMeeting.course_id == course.id)
        )
    ).scalars().all()
    objs = (
        await db_session.execute(
            select(LearningObjective).where(LearningObjective.course_id == course.id)
        )
    ).scalars().all()
    asns = (
        await db_session.execute(
            select(Assignment).where(Assignment.course_id == course.id)
        )
    ).scalars().all()

    assert len(modules) == 1
    assert len(meetings) == 1
    assert meetings[0].module_id == modules[0].id
    assert len(objs) == 1
    assert len(asns) == 1
