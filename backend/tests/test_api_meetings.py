from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User


@pytest_asyncio.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="MTGCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_create_meeting(async_client: AsyncClient, own_course: Course):
    r = await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={
            "meeting_index": 1,
            "title": "Intro",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "duration_minutes": 90,
        },
    )
    assert r.status_code == 201
    assert r.json()["data"]["status"] == "planned"


@pytest.mark.asyncio
async def test_meeting_index_unique_within_course(async_client: AsyncClient, own_course: Course):
    payload = {
        "meeting_index": 1,
        "scheduled_at": datetime.now(timezone.utc).isoformat(),
    }
    await async_client.post(f"/api/courses/{own_course.id}/meetings", json=payload)
    r = await async_client.post(f"/api/courses/{own_course.id}/meetings", json=payload)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_list_meetings_ordered_by_scheduled_at(
    async_client: AsyncClient, own_course: Course,
):
    base = datetime.now(timezone.utc)
    await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 1, "scheduled_at": (base + timedelta(days=2)).isoformat()},
    )
    await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 2, "scheduled_at": (base + timedelta(days=1)).isoformat()},
    )
    r = await async_client.get(f"/api/courses/{own_course.id}/meetings")
    data = r.json()["data"]
    assert data[0]["meeting_index"] == 2  # earlier scheduled_at first


@pytest.mark.asyncio
async def test_calendar_endpoint_combines_meetings_and_assignments(
    async_client: AsyncClient, own_course: Course,
):
    base = datetime.now(timezone.utc)
    await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 1, "scheduled_at": (base + timedelta(days=1)).isoformat(),
              "title": "Lecture 1"},
    )
    r = await async_client.get(
        f"/api/courses/{own_course.id}/calendar",
        params={
            "from_date": base.isoformat(),
            "to_date": (base + timedelta(days=7)).isoformat(),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert any(e["kind"] == "meeting" for e in body["data"])
