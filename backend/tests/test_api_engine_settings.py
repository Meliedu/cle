import uuid
import pytest
from httpx import AsyncClient

from app.models import Course, EngineOverride, Enrollment, User


@pytest.mark.asyncio
async def test_get_engine_settings_returns_default_on(
    db_session, async_client: AsyncClient, logged_in_user: User
):
    course = Course(
        name="Eng Settings",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="ENGS-1",
    )
    db_session.add(course)
    await db_session.commit()

    res = await async_client.get(f"/api/courses/{course.id}/engine")
    assert res.status_code == 200
    body = res.json()
    assert body["data"]["mode"] == "on"
    assert body["data"]["overrides_count"] == 0


@pytest.mark.asyncio
async def test_patch_engine_mode_updates_column(
    db_session, async_client: AsyncClient, logged_in_user: User
):
    course = Course(
        name="Eng Patch",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="ENGS-2",
    )
    db_session.add(course)
    await db_session.commit()

    res = await async_client.patch(
        f"/api/courses/{course.id}/engine",
        json={"mode": "random_50"},
    )
    assert res.status_code == 200
    await db_session.refresh(course)
    assert course.adaptive_engine_mode == "random_50"


@pytest.mark.asyncio
async def test_put_override_creates_row(
    db_session, async_client: AsyncClient, logged_in_user: User, test_student: User
):
    course = Course(
        name="Eng Override",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="ENGS-3",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_student.id, role="student")
    )
    await db_session.commit()

    res = await async_client.put(
        f"/api/courses/{course.id}/engine/overrides/{test_student.id}",
        json={"mode": "off"},
    )
    assert res.status_code == 200
    row = (await db_session.execute(
        __import__("sqlalchemy").select(EngineOverride).where(
            EngineOverride.user_id == test_student.id,
            EngineOverride.course_id == course.id,
        )
    )).scalar_one()
    assert row.mode == "off"


@pytest.mark.asyncio
async def test_put_override_rejects_unenrolled_user(
    db_session, async_client: AsyncClient, logged_in_user: User, test_student: User
):
    """An instructor cannot create an engine override for a student who
    isn't enrolled in their course — closes a user-UUID enumeration vector
    (probing path errors to discover valid student UUIDs).
    """
    course = Course(
        name="Eng Override Reject",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="ENGS-RJ",
    )
    db_session.add(course)
    await db_session.commit()
    # Note: test_student is intentionally NOT enrolled.

    res = await async_client.put(
        f"/api/courses/{course.id}/engine/overrides/{test_student.id}",
        json={"mode": "off"},
    )
    assert res.status_code == 404

    # Same for delete on an unenrolled user.
    res = await async_client.delete(
        f"/api/courses/{course.id}/engine/overrides/{test_student.id}"
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_put_override_upserts(
    db_session, async_client: AsyncClient, logged_in_user: User, test_student: User
):
    course = Course(
        name="Eng Upsert",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="ENGS-4",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_student.id, role="student")
    )
    db_session.add(
        EngineOverride(
            user_id=test_student.id, course_id=course.id,
            mode="off", set_by=logged_in_user.id,
        )
    )
    await db_session.commit()

    res = await async_client.put(
        f"/api/courses/{course.id}/engine/overrides/{test_student.id}",
        json={"mode": "on"},
    )
    assert res.status_code == 200
    row = (await db_session.execute(
        __import__("sqlalchemy").select(EngineOverride).where(
            EngineOverride.user_id == test_student.id,
            EngineOverride.course_id == course.id,
        )
    )).scalar_one()
    assert row.mode == "on"


@pytest.mark.asyncio
async def test_delete_override_removes_row(
    db_session, async_client: AsyncClient, logged_in_user: User, test_student: User
):
    course = Course(
        name="Eng Delete",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="ENGS-5",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_student.id, role="student")
    )
    db_session.add(
        EngineOverride(
            user_id=test_student.id, course_id=course.id,
            mode="off", set_by=logged_in_user.id,
        )
    )
    await db_session.commit()

    res = await async_client.delete(
        f"/api/courses/{course.id}/engine/overrides/{test_student.id}"
    )
    assert res.status_code == 200
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(EngineOverride).where(
            EngineOverride.user_id == test_student.id,
            EngineOverride.course_id == course.id,
        )
    )).scalars().all()
    assert rows == []
