"""Task 8: setup.py router — wizard state, analyze/analysis, publish/reopen.

The course-open gate is Decision 1: ``publish`` flips both ``setup_status`` and
``context_status``; ``reopen`` rolls back only ``setup_status`` so enrolled
students stay in (§4.8). ``SetupGateError.code`` is mapped to a structured
``detail`` the wizard branches on.

Adapted to the real conftest fixtures (``async_client`` = ``logged_in_user``
instructor; ``db_session``). ``owned_course`` is a local fixture mirroring
``test_meeting_release_endpoint.py``.
"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, Enrollment, User
from app.models.task import Task
from app.services.setup import SETUP_STEP_KEYS


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Setup Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="SETUP001",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _complete_all_steps(db_session: AsyncSession, course: Course) -> None:
    course.setup_checklist = {k: True for k in SETUP_STEP_KEYS}
    await db_session.commit()
    await db_session.refresh(course)


@pytest.mark.asyncio
async def test_get_setup_state(async_client: AsyncClient, owned_course: Course):
    r = await async_client.get(f"/api/courses/{owned_course.id}/setup")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["setup_status"] == "draft"
    assert data["context_status"] == "draft"
    assert set(data["steps"].keys()) == set(SETUP_STEP_KEYS)
    assert data["missing"] == list(SETUP_STEP_KEYS)


@pytest.mark.asyncio
async def test_patch_step_flag_moves_to_in_review(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/setup", json={"step": "basics", "done": True}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["steps"]["basics"] is True
    # auto draft -> in_review once any step is checked
    assert data["setup_status"] == "in_review"


@pytest.mark.asyncio
async def test_patch_unknown_step_rejected(
    async_client: AsyncClient, owned_course: Course
):
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/setup", json={"step": "nonsense", "done": True}
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_STEP"


@pytest.mark.asyncio
async def test_analyze_enqueues_task(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    r = await async_client.post(f"/api/courses/{owned_course.id}/setup/analyze")
    assert r.status_code == 202
    from sqlalchemy import select

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "analyze_course_setup")
        )
    ).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].payload["course_id"] == str(owned_course.id)
    assert tasks[0].status == "pending"


@pytest.mark.asyncio
async def test_get_analysis_returns_latest_result(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    # no completed task yet
    r = await async_client.get(f"/api/courses/{owned_course.id}/setup/analysis")
    assert r.status_code == 200
    assert r.json()["data"]["ready"] is False
    assert r.json()["data"]["analysis"] is None

    result = {"course_id": str(owned_course.id), "has_missing_sources": False}
    db_session.add(Task(
        task_type="analyze_course_setup",
        payload={"course_id": str(owned_course.id), "result": result},
        status="completed",
        completed_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    r = await async_client.get(f"/api/courses/{owned_course.id}/setup/analysis")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ready"] is True
    assert data["analysis"]["has_missing_sources"] is False


@pytest.mark.asyncio
async def test_publish_gate_blocks_incomplete(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    r = await async_client.post(f"/api/courses/{owned_course.id}/setup/publish")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SETUP_INCOMPLETE"
    # gate untouched by a failed publish
    await db_session.refresh(owned_course)
    assert owned_course.context_status == "draft"
    assert owned_course.setup_status == "draft"


@pytest.mark.asyncio
async def test_publish_flips_both_gates_when_complete(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    await _complete_all_steps(db_session, owned_course)
    r = await async_client.post(f"/api/courses/{owned_course.id}/setup/publish")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["setup_status"] == "published"
    assert data["context_status"] == "approved"
    await db_session.refresh(owned_course)
    assert owned_course.context_status == "approved"
    assert owned_course.context_approved_at is not None


@pytest.mark.asyncio
async def test_reopen_keeps_students_in(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    await _complete_all_steps(db_session, owned_course)
    await async_client.post(f"/api/courses/{owned_course.id}/setup/publish")
    r = await async_client.post(f"/api/courses/{owned_course.id}/setup/reopen")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["setup_status"] == "in_review"
    # §4.8: reopening does NOT lock enrolled students out
    assert data["context_status"] == "approved"


@pytest.mark.asyncio
async def test_non_owner_instructor_gets_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="setup_other_instr", email="setupother@ust.hk",
        full_name="Other Instructor", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="SETUPFOR",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=other.id, role="instructor"))
    await db_session.commit()

    # async_client is logged_in_user (a different instructor).
    r = await async_client.get(f"/api/courses/{course.id}/setup")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_student_gets_403(db_session: AsyncSession, owned_course: Course):
    student = User(
        better_auth_id="setup_student_01", email="setupstudent@connect.ust.hk",
        full_name="Setup Student", role="student",
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
            r = await ac.get(f"/api/courses/{owned_course.id}/setup")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_course_not_found_returns_404(async_client: AsyncClient):
    r = await async_client.get(f"/api/courses/{uuid.uuid4()}/setup")
    assert r.status_code == 404
