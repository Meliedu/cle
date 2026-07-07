"""P7 B11 (Decision 8a) — scan-time checkpoint status re-check.

A QR scan resolves an ``active`` ``checkpoint_launches`` row, but the launch row
alone does not prove the *checkpoint* is still launchable. If the checkpoint was
moved back to ``draft``/``archived`` (or soft-deleted) while a stale launch row
lingered ``active``, the scan MUST be refused with a typed code and NO
attendance row written. A scan against a ``published``/``live`` checkpoint still
succeeds (existing behaviour).

Participation-only is unchanged — this path never emits mastery/learning_event.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.attendance import AttendanceRecord
from app.models.checkpoint import Checkpoint
from app.models.course import Course, Enrollment
from app.models.curriculum import CourseMeeting
from app.models.user import User
from app.services.checkpoint_qr import launch_checkpoint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def launch_secret(monkeypatch):
    monkeypatch.setattr(settings, "checkpoint_token_secret", "t" * 48)
    yield


async def _setup(
    db: AsyncSession, instructor: User, student: User, *, status: str = "published"
) -> dict:
    course = Course(
        name="Recheck Course",
        language="zh",
        instructor_id=instructor.id,
        enroll_code="RC" + uuid.uuid4().hex[:6].upper(),
    )
    db.add(course)
    await db.flush()

    meeting = CourseMeeting(
        course_id=course.id, meeting_index=1, title="Session 1", scheduled_at=_utcnow()
    )
    db.add(meeting)
    await db.flush()

    cp = Checkpoint(
        course_id=course.id,
        kind="session",
        title="Session checkpoint",
        status=status,
        qr_enabled=True,
        meeting_id=meeting.id,
        release_at=_utcnow() - timedelta(hours=1),
        close_at=None,
        close_rule="manual",
    )
    db.add(cp)
    db.add(
        Enrollment(
            course_id=course.id, user_id=student.id, role="student", status="active"
        )
    )
    await db.commit()
    await db.refresh(cp)
    return {"course": course, "meeting": meeting, "cp": cp}


def _student_client(db_session: AsyncSession, user: User) -> AsyncClient:
    async def override_db():
        yield db_session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer x"},
    )


async def _attendance_rows(db: AsyncSession, meeting_id, user_id) -> list:
    return (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.meeting_id == meeting_id,
                AttendanceRecord.user_id == user_id,
            )
        )
    ).scalars().all()


@pytest.mark.parametrize("moved_to", ["draft", "teacher_editing", "approved", "archived"])
@pytest.mark.asyncio
async def test_scan_refused_when_checkpoint_left_launchable_state(
    db_session: AsyncSession,
    test_instructor: User,
    test_student: User,
    launch_secret,
    moved_to: str,
):
    """An active launch whose checkpoint moved out of published/live is refused.

    The launch row is deliberately left ``active`` (simulating a lingering token
    that was never closed) — the scan-time re-check must still refuse with a
    typed 409 and write NO attendance row (participation not recorded).
    """
    made = await _setup(db_session, test_instructor, test_student)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    # Move the checkpoint out of a launchable state WITHOUT closing the launch.
    made["cp"].status = moved_to
    await db_session.commit()

    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{launch.token}")
    app.dependency_overrides.clear()

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "CHECKPOINT_NOT_LIVE"

    rows = await _attendance_rows(db_session, made["meeting"].id, test_student.id)
    assert rows == []  # participation NOT recorded


@pytest.mark.asyncio
async def test_scan_still_succeeds_for_published_checkpoint(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    made = await _setup(db_session, test_instructor, test_student, status="published")
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{launch.token}")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    rows = await _attendance_rows(db_session, made["meeting"].id, test_student.id)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_scan_still_succeeds_for_live_checkpoint(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    made = await _setup(db_session, test_instructor, test_student, status="published")
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    # A published checkpoint may transition to live and stay scannable.
    made["cp"].status = "live"
    await db_session.commit()

    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{launch.token}")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    rows = await _attendance_rows(db_session, made["meeting"].id, test_student.id)
    assert len(rows) == 1
