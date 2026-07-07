import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.course import Course


async def _course(
    db_session, instructor, *, open_=True, code="ABCD2345", active=True, mode="code"
):
    c = Course(
        name="LANG1511",
        language="zh",
        instructor_id=instructor.id,
        enroll_code=code,
        context_status="approved" if open_ else "draft",
        enroll_code_active=active,
        join_mode=mode,
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


def _student_client(db_session, student):
    async def _db():
        yield db_session

    async def _user():
        return student

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer t"},
    )


@pytest.mark.asyncio
async def test_submit_phase_persists(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(
            f"/api/courses/{c.id}/readiness/eligibility_survey?code=ABCD2345",
            json={"answers": {"prior_study": "Never"}},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_unknown_phase_422(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(
            f"/api/courses/{c.id}/readiness/bogus?code=ABCD2345", json={"answers": {}}
        )
    app.dependency_overrides.clear()
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_PHASE"


@pytest.mark.asyncio
async def test_invalid_answers_422(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(
            f"/api/courses/{c.id}/readiness/eligibility_survey?code=ABCD2345",
            json={"answers": {"totally_unknown_question": "x"}},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_ANSWERS"


@pytest.mark.asyncio
async def test_short_preview_requires_valid_code(
    db_session, test_instructor, test_student
):
    c = await _course(db_session, test_instructor, code="ABCD2345")
    async with _student_client(db_session, test_student) as ac:
        ok = await ac.get(f"/api/courses/{c.id}/preview?code=ABCD2345&depth=short")
        bad = await ac.get(f"/api/courses/{c.id}/preview?code=WRONG999&depth=short")
    app.dependency_overrides.clear()
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["depth"] == "short"
    assert bad.status_code == 404


@pytest.mark.asyncio
async def test_inactive_code_preview_404(db_session, test_instructor, test_student):
    # Decision 4/S004: an inactive enroll code does not grant preview visibility.
    c = await _course(db_session, test_instructor, code="ABCD2345", active=False)
    async with _student_client(db_session, test_student) as ac:
        r = await ac.get(f"/api/courses/{c.id}/preview?code=ABCD2345&depth=short")
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_deep_preview_returns_detail(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, code="ABCD2345")
    async with _student_client(db_session, test_student) as ac:
        r = await ac.get(f"/api/courses/{c.id}/preview?code=ABCD2345&depth=deep")
    app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["depth"] == "deep"
    assert data["detail"] is not None
    assert "sessions" in data["detail"]
    assert "objectives" in data["detail"]


@pytest.mark.asyncio
async def test_deep_preview_not_open_409(db_session, test_instructor, test_student):
    # Decision 3: deep preview is gated behind assert_course_open -> S012.
    c = await _course(db_session, test_instructor, code="ABCD2345", open_=False)
    async with _student_client(db_session, test_student) as ac:
        r = await ac.get(f"/api/courses/{c.id}/preview?code=ABCD2345&depth=deep")
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SETUP_NOT_OPEN"


@pytest.mark.asyncio
async def test_summary_lists_completed(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    async with _student_client(db_session, test_student) as ac:
        await ac.post(
            f"/api/courses/{c.id}/readiness/eligibility_survey?code=ABCD2345",
            json={"answers": {}},
        )
        r = await ac.get(f"/api/courses/{c.id}/readiness/summary?code=ABCD2345")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert "eligibility_survey" in r.json()["data"]["completed_phases"]


@pytest.mark.asyncio
async def test_auth_required(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)

    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    # No get_current_user override + no bearer token -> 401.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get(f"/api/courses/{c.id}/preview?code=ABCD2345")
    app.dependency_overrides.clear()
    assert r.status_code == 401
