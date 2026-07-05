from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User


@pytest_asyncio.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="T", language="english",
        instructor_id=logged_in_user.id, enroll_code="ASSCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_create_assignment(async_client: AsyncClient, own_course: Course):
    due = datetime.now(timezone.utc) + timedelta(days=7)
    r = await async_client.post(
        f"/api/courses/{own_course.id}/assignments",
        json={
            "title": "Essay 1",
            "kind": "essay",
            "due_at": due.isoformat(),
            "weight": "15.00",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["data"]["is_published"] is False
    assert body["data"]["weight"] == "15.00"


@pytest.mark.asyncio
async def test_publish_assignment_via_update(async_client: AsyncClient, own_course: Course):
    due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    create = await async_client.post(
        f"/api/courses/{own_course.id}/assignments",
        json={"title": "Quiz 1", "kind": "quiz", "due_at": due},
    )
    aid = create.json()["data"]["id"]
    upd = await async_client.put(
        f"/api/courses/{own_course.id}/assignments/{aid}",
        json={"is_published": True},
    )
    assert upd.status_code == 200
    assert upd.json()["data"]["is_published"] is True
