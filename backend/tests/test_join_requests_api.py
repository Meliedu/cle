import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.course import Course, Enrollment
from app.models.user import User


async def _course(db_session, instructor, **kw):
    defaults = dict(
        name="LANG1511",
        language="zh",
        instructor_id=instructor.id,
        enroll_code="ABCD2345",
        context_status="approved",
        join_mode="code_plus_approval",
    )
    defaults.update(kw)
    c = Course(**defaults)
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=c.id, user_id=instructor.id, role="instructor", status="active")
    )
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _pending(db_session, course, student):
    e = Enrollment(
        course_id=course.id, user_id=student.id, role="student", status="pending"
    )
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)
    return e


def _client(db_session, user):
    async def _db():
        yield db_session

    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer t"},
    )


async def _make_student(db_session, suffix):
    u = User(
        better_auth_id=f"dev_student_{suffix}",
        email=f"student_{suffix}@connect.ust.hk",
        full_name=f"Student {suffix}",
        role="student",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_list_join_requests_returns_only_pending(
    db_session, test_instructor, test_student
):
    course = await _course(db_session, test_instructor)
    await _pending(db_session, course, test_student)
    # An already-active student should NOT appear in join-requests.
    active_student = await _make_student(db_session, "active01")
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=active_student.id, role="student", status="active"
        )
    )
    await db_session.commit()

    async with _client(db_session, test_instructor) as ac:
        r = await ac.get(f"/api/courses/{course.id}/join-requests")
    app.dependency_overrides.clear()

    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["user_id"] == str(test_student.id)
    assert data[0]["status"] == "pending"
    assert data[0]["email"] == test_student.email


@pytest.mark.asyncio
async def test_approve_flips_pending_to_active_and_student_sees_course(
    db_session, test_instructor, test_student
):
    course = await _course(db_session, test_instructor)
    enr = await _pending(db_session, course, test_student)

    async with _client(db_session, test_instructor) as ac:
        r = await ac.post(f"/api/courses/{course.id}/join-requests/{enr.id}/approve")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "active"

    row = (
        await db_session.execute(
            select(Enrollment).where(Enrollment.id == enr.id)
        )
    ).scalar_one()
    await db_session.refresh(row)
    assert row.status == "active"

    # Student can now read the workspace.
    async with _client(db_session, test_student) as ac:
        g = await ac.get(f"/api/courses/{course.id}")
    app.dependency_overrides.clear()
    assert g.status_code == 200


@pytest.mark.asyncio
async def test_deny_flips_pending_to_rejected(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    enr = await _pending(db_session, course, test_student)

    async with _client(db_session, test_instructor) as ac:
        r = await ac.post(f"/api/courses/{course.id}/join-requests/{enr.id}/deny")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "rejected"

    row = (
        await db_session.execute(select(Enrollment).where(Enrollment.id == enr.id))
    ).scalar_one()
    await db_session.refresh(row)
    assert row.status == "rejected"

    # Rejected student still cannot read the workspace.
    async with _client(db_session, test_student) as ac:
        g = await ac.get(f"/api/courses/{course.id}")
    app.dependency_overrides.clear()
    assert g.status_code == 404


@pytest.mark.asyncio
async def test_approve_non_pending_returns_409(
    db_session, test_instructor, test_student
):
    course = await _course(db_session, test_instructor)
    enr = await _pending(db_session, course, test_student)

    async with _client(db_session, test_instructor) as ac:
        first = await ac.post(f"/api/courses/{course.id}/join-requests/{enr.id}/approve")
        assert first.status_code == 200
        second = await ac.post(f"/api/courses/{course.id}/join-requests/{enr.id}/approve")
    app.dependency_overrides.clear()

    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "NOT_PENDING"


@pytest.mark.asyncio
async def test_deny_non_pending_returns_409(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    enr = await _pending(db_session, course, test_student)

    async with _client(db_session, test_instructor) as ac:
        await ac.post(f"/api/courses/{course.id}/join-requests/{enr.id}/deny")
        again = await ac.post(f"/api/courses/{course.id}/join-requests/{enr.id}/deny")
    app.dependency_overrides.clear()

    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "NOT_PENDING"


@pytest.mark.asyncio
async def test_missing_enrollment_returns_404(db_session, test_instructor):
    import uuid

    course = await _course(db_session, test_instructor)
    async with _client(db_session, test_instructor) as ac:
        r = await ac.post(
            f"/api/courses/{course.id}/join-requests/{uuid.uuid4()}/approve"
        )
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_roster_lists_active_students(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    # active student
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=test_student.id, role="student", status="active"
        )
    )
    # pending student (should not be in roster)
    pending_student = await _make_student(db_session, "pending01")
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=pending_student.id, role="student", status="pending"
        )
    )
    await db_session.commit()

    async with _client(db_session, test_instructor) as ac:
        r = await ac.get(f"/api/courses/{course.id}/roster")
    app.dependency_overrides.clear()

    assert r.status_code == 200
    data = r.json()["data"]
    user_ids = {row["user_id"] for row in data}
    # instructor (active) + active student both listed; pending student excluded.
    assert str(test_student.id) in user_ids
    assert str(pending_student.id) not in user_ids


@pytest.mark.asyncio
async def test_non_owner_instructor_forbidden(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    enr = await _pending(db_session, course, test_student)

    other = User(
        better_auth_id="dev_instructor_other",
        email="other@ust.hk",
        full_name="Other Instructor",
        role="instructor",
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    async with _client(db_session, other) as ac:
        listed = await ac.get(f"/api/courses/{course.id}/join-requests")
        approved = await ac.post(
            f"/api/courses/{course.id}/join-requests/{enr.id}/approve"
        )
        roster = await ac.get(f"/api/courses/{course.id}/roster")
    app.dependency_overrides.clear()

    assert listed.status_code == 404
    assert approved.status_code == 404
    assert roster.status_code == 404


@pytest.mark.asyncio
async def test_student_forbidden(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    await _pending(db_session, course, test_student)

    async with _client(db_session, test_student) as ac:
        listed = await ac.get(f"/api/courses/{course.id}/join-requests")
        roster = await ac.get(f"/api/courses/{course.id}/roster")
    app.dependency_overrides.clear()

    # require_instructor guard → 403 for a student.
    assert listed.status_code == 403
    assert roster.status_code == 403
