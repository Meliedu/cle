"""Tests for the syllabus grounding loader."""

from datetime import datetime, timezone

import pytest

from app.services.syllabus_grounding import load_syllabus_grounding


@pytest.mark.asyncio
async def test_returns_none_when_no_applied_import(db_session, test_instructor):
    from app.models import Course

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="SG001",
    )
    db_session.add(course)
    await db_session.commit()
    res = await load_syllabus_grounding(db_session, course.id)
    assert res is None


@pytest.mark.asyncio
async def test_returns_latest_applied(db_session, test_instructor):
    from app.models import Course, SyllabusImport

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="SG002",
    )
    db_session.add(course)
    await db_session.commit()

    older = SyllabusImport(
        course_id=course.id,
        raw_text="...",
        parsed_payload={"course": {"name": "old"}, "objectives": []},
        status="applied",
        applied_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        applied_by=test_instructor.id,
        created_by=test_instructor.id,
    )
    newer = SyllabusImport(
        course_id=course.id,
        raw_text="...",
        parsed_payload={
            "course": {"name": "new"},
            "objectives": [
                {
                    "scope": "course",
                    "statement": "Apply Big-O",
                    "bloom_level": "apply",
                }
            ],
        },
        status="applied",
        applied_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        applied_by=test_instructor.id,
        created_by=test_instructor.id,
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    res = await load_syllabus_grounding(db_session, course.id)
    assert res is not None
    assert "Apply Big-O" in res
