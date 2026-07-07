"""Task 9 support: GET /courses/lookup — non-committing join-code resolver.

The student join funnel (S003 code entry) needs to turn a typed code into a
``course_id`` + branch signals *without* creating an enrollment, so it can
distinguish invalid (404) from inactive (200, ``code_active=False``) before the
student invests in the readiness survey. Unknown/malformed codes 404 (no
existence leak); a deactivated code still resolves 200 so S004 shows the right
copy.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.course import Course


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
async def test_lookup_valid_code_returns_signals(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, join_mode="code_plus_approval")
    async with _client(db_session, test_student) as ac:
        r = await ac.get("/api/courses/lookup?code=ABCD2345")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["course_id"] == str(c.id)
    assert data["name"] == "LANG1511"
    assert data["is_open"] is True
    assert data["code_active"] is True
    assert data["join_mode"] == "code_plus_approval"


@pytest.mark.asyncio
async def test_lookup_normalizes_lowercase_and_spaces(db_session, test_instructor, test_student):
    await _course(db_session, test_instructor)
    async with _client(db_session, test_student) as ac:
        r = await ac.get("/api/courses/lookup?code=abcd-2345")
    app.dependency_overrides.clear()
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_lookup_unknown_code_404(db_session, test_instructor, test_student):
    await _course(db_session, test_instructor, enroll_code="ABCD2345")
    async with _client(db_session, test_student) as ac:
        r = await ac.get("/api/courses/lookup?code=ZZZZ9999")
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_lookup_malformed_code_404(db_session, test_instructor, test_student):
    await _course(db_session, test_instructor)
    async with _client(db_session, test_student) as ac:
        r = await ac.get("/api/courses/lookup?code=SHORT")
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_lookup_inactive_code_resolves_with_flag(db_session, test_instructor, test_student):
    # A known-but-deactivated code still resolves 200 so S004 can distinguish
    # inactive from invalid.
    c = await _course(db_session, test_instructor, enroll_code_active=False)
    async with _client(db_session, test_student) as ac:
        r = await ac.get("/api/courses/lookup?code=ABCD2345")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["course_id"] == str(c.id)
    assert data["code_active"] is False


@pytest.mark.asyncio
async def test_lookup_draft_course_reports_not_open(db_session, test_instructor, test_student):
    await _course(db_session, test_instructor, context_status="draft")
    async with _client(db_session, test_student) as ac:
        r = await ac.get("/api/courses/lookup?code=ABCD2345")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["data"]["is_open"] is False
