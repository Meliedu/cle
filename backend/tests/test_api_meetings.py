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


# ---------------------------------------------------------------------------
# Fix 2: Calendar accessible to enrolled students, blocked for non-enrolled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_student_enrolled_can_fetch_calendar(
    db_session: AsyncSession, logged_in_user: User,
):
    """An enrolled student should be able to fetch the calendar (Fix 2)."""
    student = User(
        better_auth_id="cal_student_01", email="calstudent@connect.ust.hk",
        full_name="Cal Student", role="student",
    )
    db_session.add(student)
    await db_session.flush()

    course = Course(
        name="CalCourse", language="english",
        instructor_id=logged_in_user.id, enroll_code="CALCRS01",
    )
    db_session.add(course)
    await db_session.flush()
    # Enroll both instructor and student so _accessible_course query succeeds
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    db_session.add(Enrollment(course_id=course.id, user_id=student.id, role="student"))
    await db_session.commit()

    async def override_db():
        yield db_session

    async def override_user():
        return student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        base = datetime.now(timezone.utc)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.get(
                f"/api/courses/{course.id}/calendar",
                params={
                    "from_date": base.isoformat(),
                    "to_date": (base + timedelta(days=7)).isoformat(),
                },
            )
            assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_non_enrolled_user_cannot_fetch_calendar(
    db_session: AsyncSession, logged_in_user: User,
):
    """A user not enrolled in the course gets 404 on the calendar (Fix 2)."""
    stranger = User(
        better_auth_id="cal_stranger_01", email="stranger@connect.ust.hk",
        full_name="Stranger", role="student",
    )
    db_session.add(stranger)
    await db_session.flush()

    course = Course(
        name="PrivateCourse", language="english",
        instructor_id=logged_in_user.id, enroll_code="PRVCRS01",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    await db_session.commit()

    async def override_db():
        yield db_session

    async def override_user():
        return stranger

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        base = datetime.now(timezone.utc)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.get(
                f"/api/courses/{course.id}/calendar",
                params={
                    "from_date": base.isoformat(),
                    "to_date": (base + timedelta(days=7)).isoformat(),
                },
            )
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_sees_only_published_assignments_in_calendar(
    db_session: AsyncSession, logged_in_user: User,
):
    """Students should not see unpublished assignments in the calendar (Fix 2)."""
    student = User(
        better_auth_id="cal_student_02", email="calstudent2@connect.ust.hk",
        full_name="Cal Student 2", role="student",
    )
    db_session.add(student)
    await db_session.flush()

    course = Course(
        name="PubCalCourse", language="english",
        instructor_id=logged_in_user.id, enroll_code="PUBCAL01",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    db_session.add(Enrollment(course_id=course.id, user_id=student.id, role="student"))

    base = datetime.now(timezone.utc)
    # published assignment — student should see this
    pub_asn = Assignment(
        course_id=course.id, title="Public HW", kind="essay",
        due_at=base + timedelta(days=2),
        is_published=True, created_by=logged_in_user.id,
    )
    # unpublished assignment — student should NOT see this
    priv_asn = Assignment(
        course_id=course.id, title="Private HW", kind="essay",
        due_at=base + timedelta(days=3),
        is_published=False, created_by=logged_in_user.id,
    )
    db_session.add_all([pub_asn, priv_asn])
    await db_session.commit()

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
            r = await ac.get(
                f"/api/courses/{course.id}/calendar",
                params={
                    "from_date": base.isoformat(),
                    "to_date": (base + timedelta(days=7)).isoformat(),
                },
            )
            assert r.status_code == 200
            titles = [e["title"] for e in r.json()["data"] if e["kind"] == "assignment"]
            assert "Public HW" in titles
            assert "Private HW" not in titles
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_sees_unpublished_assignments_in_calendar(
    async_client: AsyncClient, own_course: Course, db_session: AsyncSession,
    logged_in_user: User,
):
    """The course instructor should see unpublished assignments in the calendar (Fix 2)."""
    base = datetime.now(timezone.utc)
    priv_asn = Assignment(
        course_id=own_course.id, title="Draft HW", kind="essay",
        due_at=base + timedelta(days=2),
        is_published=False, created_by=logged_in_user.id,
    )
    db_session.add(priv_asn)
    await db_session.commit()

    r = await async_client.get(
        f"/api/courses/{own_course.id}/calendar",
        params={
            "from_date": base.isoformat(),
            "to_date": (base + timedelta(days=7)).isoformat(),
        },
    )
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()["data"] if e["kind"] == "assignment"]
    assert "Draft HW" in titles


# ---------------------------------------------------------------------------
# Fix 9: update_meeting returns 409 on meeting_index conflict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_meeting_index_conflict_returns_409(
    async_client: AsyncClient, own_course: Course,
):
    """Updating a meeting to an already-used meeting_index returns 409 (Fix 9)."""
    base = datetime.now(timezone.utc)
    # Create two meetings
    r1 = await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 1, "scheduled_at": (base + timedelta(days=1)).isoformat()},
    )
    assert r1.status_code == 201
    r2 = await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 2, "scheduled_at": (base + timedelta(days=2)).isoformat()},
    )
    assert r2.status_code == 201
    meeting2_id = r2.json()["data"]["id"]

    # Try to update meeting 2 to have meeting_index=1 (conflict)
    r = await async_client.put(
        f"/api/courses/{own_course.id}/meetings/{meeting2_id}",
        json={"meeting_index": 1},
    )
    assert r.status_code == 409
