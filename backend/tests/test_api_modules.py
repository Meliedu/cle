import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User


@pytest_asyncio.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Acct 101", language="english",
        instructor_id=logged_in_user.id, enroll_code="OWNCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_create_module(async_client: AsyncClient, own_course: Course):
    r = await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True
    assert body["data"]["name"] == "Week 1"
    assert body["data"]["order_index"] == 1


@pytest.mark.asyncio
async def test_list_modules_returns_only_own_course(
    async_client: AsyncClient, own_course: Course,
):
    await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    r = await async_client.get(f"/api/courses/{own_course.id}/modules")
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1


@pytest.mark.asyncio
async def test_create_module_on_other_instructors_course_forbidden(
    async_client: AsyncClient, db_session: AsyncSession,
):
    other = User(
        better_auth_id="other_instr", email="other@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    foreign = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="FOREIGN1",
    )
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    r = await async_client.post(
        f"/api/courses/{foreign.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    assert r.status_code == 404  # 404 not 403 to avoid course-existence leak


@pytest.mark.asyncio
async def test_update_module(async_client: AsyncClient, own_course: Course):
    create = await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    module_id = create.json()["data"]["id"]
    r = await async_client.put(
        f"/api/courses/{own_course.id}/modules/{module_id}",
        json={"name": "Week 1 — Intro"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "Week 1 — Intro"


@pytest.mark.asyncio
async def test_delete_module_soft_deletes(async_client: AsyncClient, own_course: Course):
    create = await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    module_id = create.json()["data"]["id"]
    r = await async_client.delete(
        f"/api/courses/{own_course.id}/modules/{module_id}",
    )
    assert r.status_code == 200
    listing = await async_client.get(f"/api/courses/{own_course.id}/modules")
    assert listing.json()["data"] == []
