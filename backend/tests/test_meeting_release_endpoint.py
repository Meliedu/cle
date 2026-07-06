"""Task 7: PATCH /meetings/{id}/release-state — schedule-and-venue step.

The schedule step (T018) sets venue via the existing meeting update; the
``release_state`` visibility axis (Decision 2) transitions through this
dedicated guarded endpoint with a validated transition map. It also lets the
teacher set ``topic_summary`` alongside the release in one call.
"""
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, CourseMeeting, Enrollment, User


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Release Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="RELCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _make_meeting(
    db_session: AsyncSession, course: Course, *, index: int = 1,
    release_state: str = "locked",
) -> CourseMeeting:
    meeting = CourseMeeting(
        course_id=course.id, meeting_index=index,
        scheduled_at=datetime.now(timezone.utc), release_state=release_state,
    )
    db_session.add(meeting)
    await db_session.commit()
    await db_session.refresh(meeting)
    return meeting


@pytest.mark.asyncio
async def test_instructor_can_release_and_set_topic_summary(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
):
    meeting = await _make_meeting(db_session, owned_course)
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/meetings/{meeting.id}/release-state",
        json={"release_state": "released", "topic_summary": "Tones and greetings"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["release_state"] == "released"
    assert data["topic_summary"] == "Tones and greetings"


@pytest.mark.asyncio
async def test_release_without_topic_summary_leaves_it_unchanged(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
):
    meeting = await _make_meeting(db_session, owned_course)
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/meetings/{meeting.id}/release-state",
        json={"release_state": "released"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["release_state"] == "released"
    assert r.json()["data"]["topic_summary"] is None


@pytest.mark.asyncio
async def test_illegal_transition_rejected(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
):
    # archived is terminal — archived->released is nonsense (Decision 2).
    meeting = await _make_meeting(db_session, owned_course, release_state="archived")
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/meetings/{meeting.id}/release-state",
        json={"release_state": "released"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ILLEGAL_RELEASE_TRANSITION"
    # state unchanged after a rejected transition
    await db_session.refresh(meeting)
    assert meeting.release_state == "archived"


@pytest.mark.asyncio
async def test_locked_to_completed_rejected(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
):
    meeting = await _make_meeting(db_session, owned_course)
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/meetings/{meeting.id}/release-state",
        json={"release_state": "completed"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_invalid_release_state_value_rejected(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
):
    meeting = await _make_meeting(db_session, owned_course)
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/meetings/{meeting.id}/release-state",
        json={"release_state": "nonsense"},
    )
    assert r.status_code == 422  # schema boundary validation


@pytest.mark.asyncio
async def test_non_owner_instructor_gets_404(
    async_client: AsyncClient, db_session: AsyncSession, logged_in_user: User,
):
    """A different instructor owns the course → 404 (does not leak existence)."""
    other = User(
        better_auth_id="rel_other_instr", email="other@ust.hk",
        full_name="Other Instructor", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="FORCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=other.id, role="instructor"))
    meeting = CourseMeeting(
        course_id=course.id, meeting_index=1,
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(meeting)
    await db_session.commit()

    # async_client is logged_in_user (a different instructor).
    r = await async_client.patch(
        f"/api/courses/{course.id}/meetings/{meeting.id}/release-state",
        json={"release_state": "released"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_student_gets_403(
    db_session: AsyncSession, owned_course: Course,
):
    meeting = await _make_meeting(db_session, owned_course)
    student = User(
        better_auth_id="rel_student_01", email="relstudent@connect.ust.hk",
        full_name="Rel Student", role="student",
    )
    db_session.add(student)
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
            r = await ac.patch(
                f"/api/courses/{owned_course.id}/meetings/{meeting.id}/release-state",
                json={"release_state": "released"},
            )
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_meeting_not_found_returns_404(
    async_client: AsyncClient, owned_course: Course,
):
    import uuid
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/meetings/{uuid.uuid4()}/release-state",
        json={"release_state": "released"},
    )
    assert r.status_code == 404
