import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User


@pytest_asyncio.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="T", language="english",
        instructor_id=logged_in_user.id, enroll_code="OBJCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_create_course_level_objective(async_client: AsyncClient, own_course: Course):
    r = await async_client.post(
        f"/api/courses/{own_course.id}/objectives",
        json={"statement": "Identify cost types", "bloom_level": "understand"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["data"]["module_id"] is None
    assert body["data"]["meeting_id"] is None


@pytest.mark.asyncio
async def test_objective_cannot_have_both_module_and_meeting(
    async_client: AsyncClient, own_course: Course,
):
    m = await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "W1", "order_index": 1},
    )
    module_id = m.json()["data"]["id"]
    from datetime import datetime, timezone
    mt = await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 1, "scheduled_at": datetime.now(timezone.utc).isoformat()},
    )
    meeting_id = mt.json()["data"]["id"]

    r = await async_client.post(
        f"/api/courses/{own_course.id}/objectives",
        json={
            "statement": "x",
            "module_id": module_id,
            "meeting_id": meeting_id,
        },
    )
    assert r.status_code == 400
