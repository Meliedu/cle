from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Assignment, Course, Enrollment, User


@pytest_asyncio.fixture
async def published_assignment(
    db_session: AsyncSession, logged_in_user: User, test_student: User,
) -> tuple[Course, Assignment]:
    course = Course(
        name="T", language="english",
        instructor_id=logged_in_user.id, enroll_code="SUBCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    a = Assignment(
        course_id=course.id, title="A", kind="essay",
        due_at=datetime.now(timezone.utc) + timedelta(days=3),
        is_published=True, created_by=logged_in_user.id,
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return course, a


@pytest.mark.asyncio
async def test_student_can_submit_own_submission(
    db_session: AsyncSession, test_student: User,
    published_assignment: tuple[Course, Assignment],
):
    course, assignment = published_assignment

    async def override_db():
        yield db_session

    async def override_user():
        return test_student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{course.id}/assignments/{assignment.id}/submission",
                json={"status": "submitted", "submission_payload": {"text": "hi"}},
            )
            assert r.status_code == 200
            assert r.json()["data"]["status"] == "submitted"
            assert r.json()["data"]["submitted_at"] is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_can_grade_submission(
    db_session: AsyncSession, logged_in_user: User, test_student: User,
    published_assignment: tuple[Course, Assignment],
):
    from app.models import AssignmentSubmission
    course, assignment = published_assignment
    sub = AssignmentSubmission(
        assignment_id=assignment.id, user_id=test_student.id, status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    async def override_db():
        yield db_session

    async def override_user():
        return logged_in_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{course.id}/assignments/{assignment.id}/submissions/{sub.id}/grade",
                json={"score": "85.00", "feedback": "Good", "status": "graded"},
            )
            assert r.status_code == 200
            assert r.json()["data"]["status"] == "graded"
            assert r.json()["data"]["score"] == "85.00"
    finally:
        app.dependency_overrides.clear()
