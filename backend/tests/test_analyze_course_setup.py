"""Tests for the ``analyze_course_setup`` job (course map + missing-source
detection). Read-only aggregation: builds the course map from documents,
meetings, objectives + applied-syllabus state and flags missing sources."""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.course import Course
from app.models.curriculum import CourseMeeting, LearningObjective, SyllabusImport
from app.models.document import Document
from app.models.task import Task
from app.services.setup_analysis import run_analyze_course_setup
from app.services.worker import complete_task, process_task


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="ANLZ" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest_asyncio.fixture
async def make_objective(db_session):
    async def _make(course, statement="Objective", **kwargs):
        obj = LearningObjective(
            course_id=course.id, statement=statement, **kwargs
        )
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)
        return obj

    return _make


async def _add_document(db_session, course, instructor):
    doc = Document(
        course_id=course.id,
        uploaded_by=instructor.id,
        filename="ch1.pdf",
        file_type="pdf",
        r2_key=f"docs/{uuid.uuid4()}",
        file_size=1024,
        status="completed",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_analyze_flags_objectives_without_sources(
    db_session, seed_course, make_objective
):
    await make_objective(seed_course, statement="Order food in Mandarin")
    result = await run_analyze_course_setup(
        db_session, {"course_id": str(seed_course.id)}
    )
    assert result["course_id"] == str(seed_course.id)
    assert result["counts"]["objectives"] == 1
    # No chunks/materials seeded -> objective is a missing source
    assert any(
        m["kind"] == "objective_without_source" for m in result["missing_sources"]
    )
    assert result["has_missing_sources"] is True


@pytest.mark.asyncio
async def test_analyze_clean_when_no_gaps(db_session, seed_course):
    result = await run_analyze_course_setup(
        db_session, {"course_id": str(seed_course.id)}
    )
    assert result["counts"]["objectives"] == 0
    assert result["counts"]["documents"] == 0
    assert result["counts"]["meetings"] == 0
    assert result["missing_sources"] == []
    assert result["has_missing_sources"] is False
    assert result["syllabus_applied"] is False


@pytest.mark.asyncio
async def test_analyze_objective_not_flagged_when_material_present(
    db_session, seed_course, make_objective, test_instructor
):
    await make_objective(seed_course, statement="Order food in Mandarin")
    await _add_document(db_session, seed_course, test_instructor)
    result = await run_analyze_course_setup(
        db_session, {"course_id": str(seed_course.id)}
    )
    assert result["counts"]["documents"] == 1
    # A document exists -> objective is no longer flagged as source-less
    assert not any(
        m["kind"] == "objective_without_source" for m in result["missing_sources"]
    )
    assert result["has_missing_sources"] is False


@pytest.mark.asyncio
async def test_analyze_flags_session_without_material(db_session, seed_course):
    meeting = CourseMeeting(
        course_id=seed_course.id,
        meeting_index=1,
        title="Greetings",
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(meeting)
    await db_session.commit()
    result = await run_analyze_course_setup(
        db_session, {"course_id": str(seed_course.id)}
    )
    assert result["counts"]["meetings"] == 1
    assert any(
        m["kind"] == "session_without_material" for m in result["missing_sources"]
    )
    assert result["has_missing_sources"] is True


@pytest.mark.asyncio
async def test_analyze_reports_applied_syllabus(
    db_session, seed_course, test_instructor
):
    imp = SyllabusImport(
        course_id=seed_course.id,
        raw_text="Week 1: greetings",
        status="applied",
        applied_at=datetime.now(timezone.utc),
        created_by=test_instructor.id,
    )
    db_session.add(imp)
    await db_session.commit()
    result = await run_analyze_course_setup(
        db_session, {"course_id": str(seed_course.id)}
    )
    assert result["syllabus_applied"] is True


@pytest.mark.asyncio
async def test_worker_dispatch_runs_analyze_and_stores_result(
    db_session, seed_course, make_objective
):
    """End-to-end: a Task row flows through worker.process_task dispatch and the
    course map lands in ``payload['result']`` for ``GET .../setup/analysis``."""
    await make_objective(seed_course, statement="Introduce yourself")
    task = Task(
        task_type="analyze_course_setup",
        payload={"course_id": str(seed_course.id)},
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    result = await process_task(db_session, task)
    await complete_task(db_session, task.id, result)

    await db_session.refresh(task)
    assert task.status == "completed"
    stored = task.payload["result"]
    assert stored["course_id"] == str(seed_course.id)
    assert stored["counts"]["objectives"] == 1
    assert stored["has_missing_sources"] is True
