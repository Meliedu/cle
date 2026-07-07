"""P4 B7 — calendar feed merges work_items (Decision 5).

Extends the EXISTING ``GET /courses/{course_id}/calendar`` handler
(``app/api/meetings.py::calendar_feed``) which already flattens meetings +
assignments into ``{id, kind, title, at, ...}`` events. B7 adds a THIRD source:
non-deleted ``work_items`` whose ``due_at``/``close_at`` fall in
``[from_date, to_date)``, each emitted as ``kind="work_item"`` carrying
``source_kind`` and — for a STUDENT — that student's OWN
``work_item_progress.status`` (owner-scoped). A TEACHER sees the same items
WITHOUT any per-student status. The 366-day cap + ``from<to`` validation are
unchanged, and a student only ever sees their own progress overlay.

Event date choice (noted in the impl): a work_item is in-window if EITHER
``due_at`` OR ``close_at`` falls in ``[from_date, to_date)``; the event ``at`` is
``due_at`` when present, else ``close_at``.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, Enrollment, User
from app.models.work_item import WorkItem, WorkItemProgress


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Cal Course", language="english",
        instructor_id=logged_in_user.id, enroll_code="CALFEED1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest_asyncio.fixture
async def enrolled_student(db_session: AsyncSession, own_course: Course) -> User:
    student = User(
        better_auth_id="calfeed_student_01", email="calfeedstudent@connect.ust.hk",
        full_name="Cal Feed Student", role="student",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=own_course.id, user_id=student.id,
            role="student", status="active",
        )
    )
    await db_session.commit()
    await db_session.refresh(student)
    return student


async def _make_work_item(
    db_session: AsyncSession,
    course: Course,
    author: User,
    *,
    source_kind: str = "checkpoint",
    source_id: uuid.UUID | None = None,
    title: str = "Item",
    due_at: datetime | None = None,
    close_at: datetime | None = None,
    deleted: bool = False,
) -> WorkItem:
    wi = WorkItem(
        course_id=course.id,
        source_kind=source_kind,
        source_id=source_id or uuid.uuid4(),
        title=title,
        due_at=due_at,
        close_at=close_at,
        created_by=author.id,
    )
    if deleted:
        wi.deleted_at = _utcnow()
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(wi)
    return wi


async def _set_progress(
    db_session: AsyncSession, wi: WorkItem, user: User, status: str
) -> None:
    db_session.add(
        WorkItemProgress(work_item_id=wi.id, user_id=user.id, status=status)
    )
    await db_session.commit()


def _client(db_session: AsyncSession, actor: User) -> AsyncClient:
    async def override_db():
        yield db_session

    async def override_user():
        return actor

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": "Bearer x"},
    )


# ---------------------------------------------------------------------------
# work_item events emitted alongside meetings + assignments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_emits_work_item_events_for_teacher_without_status(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
):
    now = _utcnow()
    wi = await _make_work_item(
        db_session, own_course, logged_in_user,
        source_kind="checkpoint", title="Checkpoint 1",
        due_at=now + timedelta(days=1), close_at=now + timedelta(days=1),
    )

    async with _client(db_session, logged_in_user) as ac:
        r = await ac.get(
            f"/api/courses/{own_course.id}/calendar",
            params={
                "from_date": now.isoformat(),
                "to_date": (now + timedelta(days=7)).isoformat(),
            },
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    events = r.json()["data"]
    wi_events = [e for e in events if e["kind"] == "work_item"]
    assert len(wi_events) == 1
    ev = wi_events[0]
    assert ev["id"] == str(wi.id)
    assert ev["title"] == "Checkpoint 1"
    assert ev["source_kind"] == "checkpoint"
    # Teacher view carries no per-student progress overlay.
    assert "status" not in ev


@pytest.mark.asyncio
async def test_calendar_work_item_carries_student_own_progress_status(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
    enrolled_student: User,
):
    now = _utcnow()
    wi = await _make_work_item(
        db_session, own_course, logged_in_user,
        source_kind="checkpoint", title="With progress",
        due_at=now + timedelta(days=1), close_at=now + timedelta(days=1),
    )
    await _set_progress(db_session, wi, enrolled_student, "submitted")

    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(
            f"/api/courses/{own_course.id}/calendar",
            params={
                "from_date": now.isoformat(),
                "to_date": (now + timedelta(days=7)).isoformat(),
            },
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    wi_events = [e for e in r.json()["data"] if e["kind"] == "work_item"]
    assert len(wi_events) == 1
    ev = wi_events[0]
    assert ev["id"] == str(wi.id)
    assert ev["source_kind"] == "checkpoint"
    assert ev["status"] == "submitted"


@pytest.mark.asyncio
async def test_calendar_work_item_defaults_to_pending_without_progress(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
    enrolled_student: User,
):
    now = _utcnow()
    await _make_work_item(
        db_session, own_course, logged_in_user,
        title="No progress yet",
        due_at=now + timedelta(days=1), close_at=now + timedelta(days=1),
    )

    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(
            f"/api/courses/{own_course.id}/calendar",
            params={
                "from_date": now.isoformat(),
                "to_date": (now + timedelta(days=7)).isoformat(),
            },
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    wi_events = [e for e in r.json()["data"] if e["kind"] == "work_item"]
    assert len(wi_events) == 1
    assert wi_events[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_calendar_work_item_only_own_progress_overlay(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
    enrolled_student: User,
):
    """Another student's progress must not leak into the caller's calendar."""
    now = _utcnow()
    wi = await _make_work_item(
        db_session, own_course, logged_in_user,
        title="Shared item",
        due_at=now + timedelta(days=1), close_at=now + timedelta(days=1),
    )
    other = User(
        better_auth_id="calfeed_other", email="calfeedother@connect.ust.hk",
        full_name="Other", role="student",
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=own_course.id, user_id=other.id,
            role="student", status="active",
        )
    )
    await db_session.commit()
    await _set_progress(db_session, wi, other, "completed")

    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(
            f"/api/courses/{own_course.id}/calendar",
            params={
                "from_date": now.isoformat(),
                "to_date": (now + timedelta(days=7)).isoformat(),
            },
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    wi_events = [e for e in r.json()["data"] if e["kind"] == "work_item"]
    assert len(wi_events) == 1
    # Caller has no progress of their own → pending, not the other's completed.
    assert wi_events[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_calendar_excludes_deleted_and_out_of_window_work_items(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
):
    now = _utcnow()
    # In-window via due_at.
    keep = await _make_work_item(
        db_session, own_course, logged_in_user, title="Keep",
        due_at=now + timedelta(days=2), close_at=now + timedelta(days=2),
    )
    # Out of window (both dates past the to_date).
    await _make_work_item(
        db_session, own_course, logged_in_user, title="Too late",
        due_at=now + timedelta(days=30), close_at=now + timedelta(days=30),
    )
    # Soft-deleted → never appears even though in window.
    await _make_work_item(
        db_session, own_course, logged_in_user, title="Deleted",
        due_at=now + timedelta(days=2), close_at=now + timedelta(days=2),
        deleted=True,
    )

    async with _client(db_session, logged_in_user) as ac:
        r = await ac.get(
            f"/api/courses/{own_course.id}/calendar",
            params={
                "from_date": now.isoformat(),
                "to_date": (now + timedelta(days=7)).isoformat(),
            },
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    wi_events = [e for e in r.json()["data"] if e["kind"] == "work_item"]
    assert [e["title"] for e in wi_events] == ["Keep"]
    assert wi_events[0]["id"] == str(keep.id)


@pytest.mark.asyncio
async def test_calendar_work_item_in_window_via_close_at_only(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
):
    """due_at absent but close_at in window → included; event ``at`` == close_at."""
    now = _utcnow()
    close = now + timedelta(days=3)
    wi = await _make_work_item(
        db_session, own_course, logged_in_user, title="Close only",
        due_at=None, close_at=close,
    )

    async with _client(db_session, logged_in_user) as ac:
        r = await ac.get(
            f"/api/courses/{own_course.id}/calendar",
            params={
                "from_date": now.isoformat(),
                "to_date": (now + timedelta(days=7)).isoformat(),
            },
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    wi_events = [e for e in r.json()["data"] if e["kind"] == "work_item"]
    assert len(wi_events) == 1
    ev = wi_events[0]
    assert ev["id"] == str(wi.id)
    # Falls back to close_at when due_at is absent.
    assert ev["at"] == close.isoformat()


@pytest.mark.asyncio
async def test_calendar_events_sorted_by_at_across_sources(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
):
    now = _utcnow()
    # Meeting on day 3.
    await async_create_meeting(db_session, own_course, day=now + timedelta(days=3))
    # work_item on day 1 → must sort before the meeting.
    await _make_work_item(
        db_session, own_course, logged_in_user, title="Early WI",
        due_at=now + timedelta(days=1), close_at=now + timedelta(days=1),
    )

    async with _client(db_session, logged_in_user) as ac:
        r = await ac.get(
            f"/api/courses/{own_course.id}/calendar",
            params={
                "from_date": now.isoformat(),
                "to_date": (now + timedelta(days=7)).isoformat(),
            },
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    events = r.json()["data"]
    ats = [e["at"] for e in events]
    assert ats == sorted(ats)
    # The work_item (day 1) precedes the meeting (day 3).
    assert events[0]["kind"] == "work_item"


async def async_create_meeting(
    db_session: AsyncSession, course: Course, *, day: datetime
) -> None:
    from app.models import CourseMeeting

    db_session.add(
        CourseMeeting(
            course_id=course.id, meeting_index=1, title="Lecture",
            scheduled_at=day,
        )
    )
    await db_session.commit()


# ---------------------------------------------------------------------------
# Validation unchanged: from<to and the 366-day cap still apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_from_after_to_rejected(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
):
    now = _utcnow()
    async with _client(db_session, logged_in_user) as ac:
        r = await ac.get(
            f"/api/courses/{own_course.id}/calendar",
            params={
                "from_date": (now + timedelta(days=7)).isoformat(),
                "to_date": now.isoformat(),
            },
        )
    app.dependency_overrides.clear()
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_calendar_range_over_366_days_rejected(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
):
    now = _utcnow()
    async with _client(db_session, logged_in_user) as ac:
        r = await ac.get(
            f"/api/courses/{own_course.id}/calendar",
            params={
                "from_date": now.isoformat(),
                "to_date": (now + timedelta(days=400)).isoformat(),
            },
        )
    app.dependency_overrides.clear()
    assert r.status_code == 400, r.text
