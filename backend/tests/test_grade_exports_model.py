"""Model tests for ``grade_exports`` (P5 Task B2).

``grade_exports`` is an **append-only audit table** (Decision 7): every
``GET /courses/{id}/grade-export.csv`` appends exactly one row BEFORE streaming.
It is course-scoped / teacher-owned — the endpoint is owner-guarded — so there is
**NO RLS** and, being an immutable audit log, **NO soft-delete** column
(UUID PK + a plain ``created_at`` only).

This covers only the ORM columns and that a row persists and reads back, via
``Base.metadata.create_all`` in the disposable test DB (``db_session``).
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.course import Course
from app.models.score import GradeExport


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="GEXP" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_grade_export_persists_and_reads_back(
    db_session, seed_course, test_instructor
):
    export = GradeExport(
        course_id=seed_course.id,
        exported_by=test_instructor.id,
        format="csv",
        filters={"category_id": None, "purpose": "graded"},
        row_count=42,
    )
    db_session.add(export)
    await db_session.commit()
    await db_session.refresh(export)

    assert export.id is not None
    assert export.course_id == seed_course.id
    assert export.exported_by == test_instructor.id
    assert export.format == "csv"
    assert export.filters == {"category_id": None, "purpose": "graded"}
    assert export.row_count == 42
    # Append-only audit: created_at present, NO soft-delete column.
    assert export.created_at is not None
    assert not hasattr(export, "deleted_at")

    # Reads back by id.
    fetched = (
        await db_session.execute(
            select(GradeExport).where(GradeExport.id == export.id)
        )
    ).scalar_one()
    assert fetched.id == export.id
    assert fetched.row_count == 42


@pytest.mark.asyncio
async def test_grade_export_filters_nullable(
    db_session, seed_course, test_instructor
):
    """filters is a JSON column and may be NULL (no filters applied)."""
    export = GradeExport(
        course_id=seed_course.id,
        exported_by=test_instructor.id,
        format="csv",
        row_count=0,
    )
    db_session.add(export)
    await db_session.commit()
    await db_session.refresh(export)
    assert export.filters is None
    assert export.row_count == 0
