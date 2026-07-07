"""P5 B11 (Decision 7): audited CSV grade export.

`GET /courses/{id}/grade-export.csv` (owner-guarded) streams a CSV AND appends
exactly ONE ``grade_exports`` audit row (`exported_by=user.id`, `format='csv'`,
`filters`, `row_count`) in the SAME request — committed before/with the stream.
A student → 403; a non-owner teacher → 404.
"""
import csv
import io
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, Enrollment, User
from app.models.quiz import Quiz, QuizAttempt
from app.models.score import GradeExport, ScoreCategory


@pytest_asyncio.fixture
async def export_course(db_session: AsyncSession, logged_in_user: User) -> dict:
    course = Course(
        name="Export", language="english",
        instructor_id=logged_in_user.id, enroll_code="EXPORT01",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    student = User(
        better_auth_id="exp_student_01", email="expstudent@connect.ust.hk",
        full_name="Export Student", role="student",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=student.id, role="student", status="active")
    )
    cat = ScoreCategory(course_id=course.id, name="Quizzes", sort=0)
    db_session.add(cat)
    await db_session.flush()
    quiz = Quiz(
        course_id=course.id, created_by=logged_in_user.id, title="Final",
        assessment_purpose="graded", score_bearing=True,
        score_category_id=cat.id, points=Decimal("100"),
    )
    db_session.add(quiz)
    await db_session.flush()
    db_session.add(QuizAttempt(
        quiz_id=quiz.id, user_id=student.id, answers={"0": "a"},
        score=Decimal("75.00"), total_questions=4, correct_count=3,
    ))
    await db_session.commit()
    await db_session.refresh(course)
    return {"course": course, "student": student, "quiz": quiz}


@pytest.mark.asyncio
async def test_export_streams_csv(async_client: AsyncClient, export_course: dict):
    course = export_course["course"]
    r = await async_client.get(f"/api/courses/{course.id}/grade-export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "").lower()

    reader = list(csv.reader(io.StringIO(r.text)))
    header = reader[0]
    assert "student_name" in header and "email" in header
    # One data row per active student (one student here).
    data_rows = reader[1:]
    assert len(data_rows) == 1
    assert "Export Student" in data_rows[0]


@pytest.mark.asyncio
async def test_export_appends_exactly_one_audit_row(
    async_client: AsyncClient, export_course: dict, db_session: AsyncSession,
    logged_in_user: User,
):
    course = export_course["course"]

    async def _count() -> int:
        return (
            await db_session.execute(
                select(func.count()).select_from(GradeExport).where(
                    GradeExport.course_id == course.id
                )
            )
        ).scalar_one()

    assert await _count() == 0
    await async_client.get(f"/api/courses/{course.id}/grade-export.csv")
    assert await _count() == 1

    # A second export appends exactly one more (append-only, never dedupes).
    await async_client.get(f"/api/courses/{course.id}/grade-export.csv")
    assert await _count() == 2

    row = (
        await db_session.execute(
            select(GradeExport).where(GradeExport.course_id == course.id)
            .order_by(GradeExport.created_at)
        )
    ).scalars().first()
    assert row.exported_by == logged_in_user.id
    assert row.format == "csv"
    assert row.row_count == 1  # one active student
    assert row.filters is not None


@pytest.mark.asyncio
async def test_export_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="exp_other_instr", email="expother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="EXPFOR01",
    )
    db_session.add(course)
    await db_session.commit()
    r = await async_client.get(f"/api/courses/{course.id}/grade-export.csv")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_export_student_forbidden(
    db_session: AsyncSession, export_course: dict
):
    student = export_course["student"]
    course = export_course["course"]

    async def override_db():
        yield db_session

    async def override_user():
        return student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.get(f"/api/courses/{course.id}/grade-export.csv")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
