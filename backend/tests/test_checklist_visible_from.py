"""P7 B11 (Decision 9.1) — ``work_items.visible_from`` as a release gate.

A work_item with a FUTURE ``visible_from`` is hidden from BOTH the student
checklist (``checklist.py::_build_checklist``) AND the calendar feed
(``meetings.py::calendar_feed`` work_item query). A past/NULL ``visible_from``
shows.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, Enrollment, User
from app.models.work_item import WorkItem


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Visible Course",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="VIS00001",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest_asyncio.fixture
async def enrolled_student(db_session: AsyncSession, owned_course: Course) -> User:
    student = User(
        better_auth_id="vis_student_01",
        email="visstudent@connect.ust.hk",
        full_name="Vis Student",
        role="student",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=owned_course.id, user_id=student.id, role="student", status="active"
        )
    )
    await db_session.commit()
    await db_session.refresh(student)
    return student


async def _make_wi(
    db: AsyncSession,
    course: Course,
    author: User,
    *,
    title: str,
    due_at: datetime,
    visible_from: datetime | None,
) -> WorkItem:
    wi = WorkItem(
        course_id=course.id,
        source_kind="material",
        source_id=uuid.uuid4(),
        title=title,
        due_at=due_at,
        close_at=due_at,
        visible_from=visible_from,
        created_by=author.id,
    )
    db.add(wi)
    await db.commit()
    await db.refresh(wi)
    return wi


def _client(db_session: AsyncSession, actor: User) -> AsyncClient:
    async def override_db():
        yield db_session

    async def override_user():
        return actor

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer x"},
    )


@pytest.mark.asyncio
async def test_checklist_hides_future_visible_from(
    db_session: AsyncSession,
    owned_course: Course,
    logged_in_user: User,
    enrolled_student: User,
):
    now = _utcnow()
    await _make_wi(
        db_session, owned_course, logged_in_user,
        title="Released", due_at=now + timedelta(days=2),
        visible_from=now - timedelta(days=1),
    )
    await _make_wi(
        db_session, owned_course, logged_in_user,
        title="NullVisible", due_at=now + timedelta(days=3), visible_from=None,
    )
    await _make_wi(
        db_session, owned_course, logged_in_user,
        title="Future", due_at=now + timedelta(days=4),
        visible_from=now + timedelta(days=1),
    )

    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/courses/{owned_course.id}/checklist")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    titles = {item["title"] for item in r.json()["data"]}
    assert titles == {"Released", "NullVisible"}
    assert "Future" not in titles


@pytest.mark.asyncio
async def test_calendar_hides_future_visible_from(
    db_session: AsyncSession,
    owned_course: Course,
    logged_in_user: User,
    enrolled_student: User,
):
    now = _utcnow()
    await _make_wi(
        db_session, owned_course, logged_in_user,
        title="Released", due_at=now + timedelta(days=2),
        visible_from=now - timedelta(days=1),
    )
    await _make_wi(
        db_session, owned_course, logged_in_user,
        title="Future", due_at=now + timedelta(days=3),
        visible_from=now + timedelta(days=1),
    )

    from_date = (now - timedelta(days=1)).isoformat()
    to_date = (now + timedelta(days=10)).isoformat()
    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(
            f"/api/courses/{owned_course.id}/calendar",
            params={"from_date": from_date, "to_date": to_date},
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    wi_titles = {e["title"] for e in r.json()["data"] if e["kind"] == "work_item"}
    assert "Released" in wi_titles
    assert "Future" not in wi_titles
