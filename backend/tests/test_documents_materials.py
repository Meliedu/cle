"""P4 B8 — Materials library API: assign-to-session, session folders, preview.

Covers the security-sensitive materials surface (spec §4.6, Decision 6):

* ``PATCH /courses/{id}/documents/{doc_id}`` (owner-guarded) sets/clears
  ``meeting_id``; a FOREIGN meeting (another course) is refused; assigning to a
  ``released`` session creates an idempotent ``material`` work_item, unassigning
  soft-removes it.
* ``GET /courses/{id}/materials`` groups documents by ``meeting_id`` (+ an
  "unassigned" bucket for the owner) with each session's ``release_state``.
* ``GET /courses/{id}/documents/{doc_id}/preview`` returns a SHORT-LIVED signed
  R2 URL (owner OR enrolled student on a RELEASED session), never raw bytes.
"""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, CourseMeeting, Enrollment, User
from app.models.document import Document
from app.models.work_item import WorkItem


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Materials Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="MATCRSE1",
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
    release_state: str = "locked", title: str | None = None,
) -> CourseMeeting:
    meeting = CourseMeeting(
        course_id=course.id, meeting_index=index, title=title,
        scheduled_at=datetime.now(timezone.utc), release_state=release_state,
    )
    db_session.add(meeting)
    await db_session.commit()
    await db_session.refresh(meeting)
    return meeting


async def _make_document(
    db_session: AsyncSession, course: Course, uploader: User, *,
    filename: str = "lecture.pdf", meeting_id: uuid.UUID | None = None,
) -> Document:
    doc = Document(
        course_id=course.id, uploaded_by=uploader.id, filename=filename,
        file_type="pdf", file_size=1024,
        r2_key=f"courses/{course.id}/documents/{uuid.uuid4()}/{filename}",
        status="completed", kind="lecture", meeting_id=meeting_id,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


async def _active_material_work_item(
    db_session: AsyncSession, course_id: uuid.UUID, doc_id: uuid.UUID
) -> WorkItem | None:
    return (
        await db_session.execute(
            select(WorkItem).where(
                WorkItem.course_id == course_id,
                WorkItem.source_kind == "material",
                WorkItem.source_id == doc_id,
                WorkItem.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


@asynccontextmanager
async def _client_as(db_session: AsyncSession, user: User):
    async def override_db():
        yield db_session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# PATCH assign / unassign
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_document_to_meeting_sets_meeting_id(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User,
):
    meeting = await _make_meeting(db_session, owned_course)
    doc = await _make_document(db_session, owned_course, logged_in_user)

    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/documents/{doc.id}",
        json={"meeting_id": str(meeting.id)},
    )
    assert r.status_code == 200
    assert r.json()["data"]["meeting_id"] == str(meeting.id)

    await db_session.refresh(doc)
    assert doc.meeting_id == meeting.id


@pytest.mark.asyncio
async def test_unassign_document_clears_meeting_id(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User,
):
    meeting = await _make_meeting(db_session, owned_course)
    doc = await _make_document(
        db_session, owned_course, logged_in_user, meeting_id=meeting.id
    )

    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/documents/{doc.id}",
        json={"meeting_id": None},
    )
    assert r.status_code == 200
    assert r.json()["data"]["meeting_id"] is None

    await db_session.refresh(doc)
    assert doc.meeting_id is None


@pytest.mark.asyncio
async def test_assign_to_foreign_meeting_rejected(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User,
):
    """A meeting belonging to ANOTHER course must never be assignable."""
    other_course = Course(
        name="Other", language="english",
        instructor_id=logged_in_user.id, enroll_code="OTHRCRS1",
    )
    db_session.add(other_course)
    await db_session.commit()
    foreign_meeting = await _make_meeting(db_session, other_course)
    doc = await _make_document(db_session, owned_course, logged_in_user)

    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/documents/{doc.id}",
        json={"meeting_id": str(foreign_meeting.id)},
    )
    assert r.status_code in (404, 422)

    await db_session.refresh(doc)
    assert doc.meeting_id is None


@pytest.mark.asyncio
async def test_assign_to_released_session_creates_material_work_item(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User,
):
    meeting = await _make_meeting(db_session, owned_course, release_state="released")
    doc = await _make_document(db_session, owned_course, logged_in_user)

    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/documents/{doc.id}",
        json={"meeting_id": str(meeting.id)},
    )
    assert r.status_code == 200

    wi = await _active_material_work_item(db_session, owned_course.id, doc.id)
    assert wi is not None
    assert wi.source_kind == "material"
    assert wi.source_id == doc.id
    assert wi.required is False
    assert wi.score_bearing is False


@pytest.mark.asyncio
async def test_assign_to_released_session_is_idempotent(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User,
):
    meeting = await _make_meeting(db_session, owned_course, release_state="released")
    doc = await _make_document(db_session, owned_course, logged_in_user)

    for _ in range(2):
        r = await async_client.patch(
            f"/api/courses/{owned_course.id}/documents/{doc.id}",
            json={"meeting_id": str(meeting.id)},
        )
        assert r.status_code == 200

    rows = (
        await db_session.execute(
            select(WorkItem).where(
                WorkItem.course_id == owned_course.id,
                WorkItem.source_kind == "material",
                WorkItem.source_id == doc.id,
                WorkItem.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_assign_to_locked_session_creates_no_work_item(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User,
):
    meeting = await _make_meeting(db_session, owned_course, release_state="locked")
    doc = await _make_document(db_session, owned_course, logged_in_user)

    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/documents/{doc.id}",
        json={"meeting_id": str(meeting.id)},
    )
    assert r.status_code == 200
    assert await _active_material_work_item(db_session, owned_course.id, doc.id) is None


@pytest.mark.asyncio
async def test_unassign_soft_removes_material_work_item(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User,
):
    meeting = await _make_meeting(db_session, owned_course, release_state="released")
    doc = await _make_document(db_session, owned_course, logged_in_user)

    await async_client.patch(
        f"/api/courses/{owned_course.id}/documents/{doc.id}",
        json={"meeting_id": str(meeting.id)},
    )
    assert await _active_material_work_item(db_session, owned_course.id, doc.id) is not None

    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/documents/{doc.id}",
        json={"meeting_id": None},
    )
    assert r.status_code == 200
    assert await _active_material_work_item(db_session, owned_course.id, doc.id) is None


@pytest.mark.asyncio
async def test_reassign_released_after_unassign_reactivates_work_item(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User,
):
    """Soft-delete then re-assign must reactivate (not double-insert the unique key)."""
    meeting = await _make_meeting(db_session, owned_course, release_state="released")
    doc = await _make_document(db_session, owned_course, logged_in_user)
    url = f"/api/courses/{owned_course.id}/documents/{doc.id}"

    await async_client.patch(url, json={"meeting_id": str(meeting.id)})
    await async_client.patch(url, json={"meeting_id": None})
    r = await async_client.patch(url, json={"meeting_id": str(meeting.id)})
    assert r.status_code == 200
    assert await _active_material_work_item(db_session, owned_course.id, doc.id) is not None


@pytest.mark.asyncio
async def test_patch_missing_document_404(
    async_client: AsyncClient, owned_course: Course,
):
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/documents/{uuid.uuid4()}",
        json={"meeting_id": None},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_non_owner_instructor_refused(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    other = User(
        better_auth_id="mat_other_instr", email="mother@ust.hk",
        full_name="Other Instr", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    doc = await _make_document(db_session, owned_course, logged_in_user)

    async with _client_as(db_session, other) as ac:
        r = await ac.patch(
            f"/api/courses/{owned_course.id}/documents/{doc.id}",
            json={"meeting_id": None},
        )
    assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# GET /materials — grouping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_materials_grouped_by_meeting_with_release_state(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User,
):
    m1 = await _make_meeting(
        db_session, owned_course, index=1, release_state="released", title="Week 1"
    )
    m2 = await _make_meeting(
        db_session, owned_course, index=2, release_state="locked", title="Week 2"
    )
    await _make_document(
        db_session, owned_course, logged_in_user, filename="a.pdf", meeting_id=m1.id
    )
    await _make_document(
        db_session, owned_course, logged_in_user, filename="b.pdf", meeting_id=m2.id
    )
    await _make_document(db_session, owned_course, logged_in_user, filename="loose.pdf")

    r = await async_client.get(f"/api/courses/{owned_course.id}/materials")
    assert r.status_code == 200
    data = r.json()["data"]

    by_meeting = {s["meeting_id"]: s for s in data["sessions"]}
    assert by_meeting[str(m1.id)]["release_state"] == "released"
    assert by_meeting[str(m2.id)]["release_state"] == "locked"
    assert {d["filename"] for d in by_meeting[str(m1.id)]["documents"]} == {"a.pdf"}
    assert {d["filename"] for d in data["unassigned"]} == {"loose.pdf"}


@pytest.mark.asyncio
async def test_materials_student_sees_only_released_sessions(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    student = User(
        better_auth_id="mat_student_01", email="matstudent@connect.ust.hk",
        full_name="Mat Student", role="student",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=owned_course.id, user_id=student.id,
            role="student", status="active",
        )
    )
    released = await _make_meeting(
        db_session, owned_course, index=1, release_state="released"
    )
    locked = await _make_meeting(
        db_session, owned_course, index=2, release_state="locked"
    )
    await _make_document(
        db_session, owned_course, logged_in_user, filename="ok.pdf", meeting_id=released.id
    )
    await _make_document(
        db_session, owned_course, logged_in_user, filename="hidden.pdf", meeting_id=locked.id
    )
    await _make_document(db_session, owned_course, logged_in_user, filename="loose.pdf")

    async with _client_as(db_session, student) as ac:
        r = await ac.get(f"/api/courses/{owned_course.id}/materials")
    assert r.status_code == 200
    data = r.json()["data"]

    shown_meetings = {s["meeting_id"] for s in data["sessions"]}
    assert str(released.id) in shown_meetings
    assert str(locked.id) not in shown_meetings
    # No unassigned bucket for students; locked/loose files never leak.
    all_files = {
        d["filename"] for s in data["sessions"] for d in s["documents"]
    } | {d["filename"] for d in data["unassigned"]}
    assert "hidden.pdf" not in all_files
    assert "loose.pdf" not in all_files


# ---------------------------------------------------------------------------
# GET /documents/{id}/preview — signed URL
# ---------------------------------------------------------------------------

_FAKE_URL = "https://r2.example.com/signed?token=abc123"


@pytest.mark.asyncio
async def test_preview_owner_gets_signed_url(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, logged_in_user: User, monkeypatch,
):
    doc = await _make_document(db_session, owned_course, logged_in_user)
    captured = {}

    def fake_presign(r2_key, expiration=3600):
        captured["key"] = r2_key
        captured["ttl"] = expiration
        return _FAKE_URL

    monkeypatch.setattr("app.api.documents.generate_presigned_url", fake_presign)

    r = await async_client.get(
        f"/api/courses/{owned_course.id}/documents/{doc.id}/preview"
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["url"] == _FAKE_URL
    # Short-lived, and the URL is for the document's own object.
    assert captured["ttl"] <= 900
    assert captured["key"] == doc.r2_key
    # Never streams raw bytes.
    assert r.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_preview_student_on_released_session_allowed(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User, monkeypatch,
):
    student = User(
        better_auth_id="mat_prev_student", email="prevstudent@connect.ust.hk",
        full_name="Prev Student", role="student",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=owned_course.id, user_id=student.id,
            role="student", status="active",
        )
    )
    meeting = await _make_meeting(db_session, owned_course, release_state="released")
    doc = await _make_document(
        db_session, owned_course, logged_in_user, meeting_id=meeting.id
    )

    monkeypatch.setattr(
        "app.api.documents.generate_presigned_url", lambda *a, **k: _FAKE_URL
    )

    async with _client_as(db_session, student) as ac:
        r = await ac.get(
            f"/api/courses/{owned_course.id}/documents/{doc.id}/preview"
        )
    assert r.status_code == 200
    assert r.json()["data"]["url"] == _FAKE_URL


@pytest.mark.asyncio
async def test_preview_student_on_locked_session_refused(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    student = User(
        better_auth_id="mat_locked_student", email="lockedstudent@connect.ust.hk",
        full_name="Locked Student", role="student",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=owned_course.id, user_id=student.id,
            role="student", status="active",
        )
    )
    meeting = await _make_meeting(db_session, owned_course, release_state="locked")
    doc = await _make_document(
        db_session, owned_course, logged_in_user, meeting_id=meeting.id
    )

    async with _client_as(db_session, student) as ac:
        r = await ac.get(
            f"/api/courses/{owned_course.id}/documents/{doc.id}/preview"
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_preview_student_unassigned_refused(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    student = User(
        better_auth_id="mat_unassigned_student", email="unassignedstu@connect.ust.hk",
        full_name="Unassigned Student", role="student",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=owned_course.id, user_id=student.id,
            role="student", status="active",
        )
    )
    doc = await _make_document(db_session, owned_course, logged_in_user)

    async with _client_as(db_session, student) as ac:
        r = await ac.get(
            f"/api/courses/{owned_course.id}/documents/{doc.id}/preview"
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_preview_non_enrolled_student_refused(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    outsider = User(
        better_auth_id="mat_outsider", email="outsider@connect.ust.hk",
        full_name="Outsider", role="student",
    )
    db_session.add(outsider)
    await db_session.flush()
    meeting = await _make_meeting(db_session, owned_course, release_state="released")
    doc = await _make_document(
        db_session, owned_course, logged_in_user, meeting_id=meeting.id
    )

    async with _client_as(db_session, outsider) as ac:
        r = await ac.get(
            f"/api/courses/{owned_course.id}/documents/{doc.id}/preview"
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_preview_missing_document_404(
    async_client: AsyncClient, owned_course: Course,
):
    r = await async_client.get(
        f"/api/courses/{owned_course.id}/documents/{uuid.uuid4()}/preview"
    )
    assert r.status_code == 404
