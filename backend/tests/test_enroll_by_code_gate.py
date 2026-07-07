"""Task 5: enroll-by-code respects join_mode + setup gate + status (Decisions 1 & 3).

``enroll-by-code`` is the terminal join action. Gate order:
normalize/validate format -> resolve course (404, no existence leak) ->
code active? (JOIN_CODE_INACTIVE) -> course open? (assert_course_open ->
SETUP_NOT_OPEN) -> already enrolled? (idempotent, returns existing status) ->
create enrollment with status from join_mode (``code`` -> active,
``code_plus_approval`` -> pending).

Response shape (backward-compat note): the route now returns
``{course: CourseResponse, enrollment_status: str}`` instead of a bare
CourseResponse. The frontend JoinCourseDialog change is Task 9; here we only
assert the new shape so the funnel can route active -> S013 vs pending ->
pending-approval.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.course import Course, Enrollment


async def _course(db_session, instructor, **kw):
    defaults = dict(
        name="LANG1511", language="zh", instructor_id=instructor.id,
        enroll_code="ABCD2345", context_status="approved",
        enroll_code_active=True, join_mode="code",
    )
    defaults.update(kw)
    c = Course(**defaults)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


def _client(db_session, student):
    async def _db():
        yield db_session

    async def _user():
        return student

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": "Bearer t"},
    )


@pytest.mark.asyncio
async def test_code_mode_enrolls_active(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, join_mode="code")
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert r.status_code in (200, 201)
    assert r.json()["data"]["enrollment_status"] == "active"
    row = (await db_session.execute(
        select(Enrollment).where(Enrollment.course_id == c.id)
    )).scalar_one()
    assert row.status == "active"


@pytest.mark.asyncio
async def test_approval_mode_enrolls_pending(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, join_mode="code_plus_approval")
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert r.json()["data"]["enrollment_status"] == "pending"
    row = (await db_session.execute(
        select(Enrollment).where(Enrollment.course_id == c.id)
    )).scalar_one()
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_not_open_blocks_join(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, context_status="draft")
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SETUP_NOT_OPEN"
    # No enrollment row created when the gate refuses.
    rows = (await db_session.execute(
        select(Enrollment).where(Enrollment.course_id == c.id)
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_inactive_code_blocks_join(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, enroll_code_active=False)
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "JOIN_CODE_INACTIVE"


@pytest.mark.asyncio
async def test_invalid_code_rejected(db_session, test_instructor, test_student):
    # A valid-format code that resolves to no course -> 404 (no existence leak).
    await _course(db_session, test_instructor, enroll_code="ABCD2345")
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ZZZZ9999"})
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_reenroll_is_idempotent(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, join_mode="code")
    async with _client(db_session, test_student) as ac:
        first = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
        second = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert first.json()["data"]["enrollment_status"] == "active"
    # Idempotent: same active status returned, no duplicate row.
    assert second.json()["data"]["enrollment_status"] == "active"
    rows = (await db_session.execute(
        select(Enrollment).where(
            Enrollment.course_id == c.id, Enrollment.user_id == test_student.id
        )
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_pending_reenroll_returns_pending(db_session, test_instructor, test_student):
    # A pending student re-submitting the code keeps pending (not re-created).
    c = await _course(db_session, test_instructor, join_mode="code_plus_approval")
    async with _client(db_session, test_student) as ac:
        await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
        second = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert second.json()["data"]["enrollment_status"] == "pending"
    rows = (await db_session.execute(
        select(Enrollment).where(Enrollment.course_id == c.id)
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_response_shape_carries_course_and_status(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, join_mode="code")
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    data = r.json()["data"]
    assert data["enrollment_status"] == "active"
    assert data["course"]["id"] == str(c.id)
    assert data["course"]["name"] == "LANG1511"


@pytest.mark.asyncio
async def test_pending_student_cannot_read_course(db_session, test_instructor, test_student):
    # A pending (unapproved) student must not read the workspace via GET /courses/{id}.
    c = await _course(db_session, test_instructor, join_mode="code_plus_approval")
    async with _client(db_session, test_student) as ac:
        await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
        r = await ac.get(f"/api/courses/{c.id}")
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_active_student_can_read_course(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, join_mode="code")
    async with _client(db_session, test_student) as ac:
        await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
        r = await ac.get(f"/api/courses/{c.id}")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["data"]["id"] == str(c.id)
