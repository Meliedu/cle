"""P3 T10 — QR attendance scan endpoint (``POST /api/attend/{token}``).

The student scans the teacher's QR and hits this endpoint. It:

* verifies the launch token (signature + ``exp``) via ``decode_launch_token``;
* resolves the ``checkpoint_launches`` row by ``jti`` and confirms it is still
  ``active`` (revocation-on-rotate is only visible on the row, not the token);
* requires the scanning student to be *actively* enrolled in the checkpoint's
  course (mirrors ``checkpoint_responses`` enrollment scoping);
* upserts a single ``attendance_records`` row (``source='qr'``) with
  ``status=present|late`` derived from the checkpoint window — idempotent on the
  ``(meeting_id, user_id)`` unique constraint so a second scan is a 200 no-op;
* returns the checkpoint intro route so the client routes into S034.

Attendance is **participation only** — it NEVER emits a learning_event or
enqueues mastery (doc rule).
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
from app.models.attendance import AttendanceRecord, CheckpointLaunch
from app.models.checkpoint import Checkpoint
from app.models.course import Course, Enrollment
from app.models.curriculum import CourseMeeting
from app.models.user import User
from app.services.checkpoint_qr import encode_launch_token, launch_checkpoint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def launch_secret(monkeypatch):
    """A configured >=32-byte signing secret for the duration of the test."""
    monkeypatch.setattr(settings, "checkpoint_token_secret", "t" * 48)
    yield


async def _setup(
    db: AsyncSession,
    instructor: User,
    student: User,
    *,
    status: str = "published",
    close_at: datetime | None = None,
    enroll: bool = True,
) -> dict:
    course = Course(
        name="Scan Course",
        language="zh",
        instructor_id=instructor.id,
        enroll_code="SC" + uuid.uuid4().hex[:6].upper(),
    )
    db.add(course)
    await db.flush()

    meeting = CourseMeeting(
        course_id=course.id,
        meeting_index=1,
        title="Session 1",
        scheduled_at=_utcnow(),
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
        close_at=close_at,
        close_rule="manual",
    )
    db.add(cp)
    if enroll:
        db.add(
            Enrollment(
                course_id=course.id,
                user_id=student.id,
                role="student",
                status="active",
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


# ----- happy path: present -----

@pytest.mark.asyncio
async def test_scan_records_present(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    made = await _setup(db_session, test_instructor, test_student)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{launch.token}")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "present"
    assert data["source"] == "qr"
    assert data["checkpoint_id"] == str(made["cp"].id)
    assert data["meeting_id"] == str(made["meeting"].id)
    assert data["intro_route"] == f"/api/checkpoints/{made['cp'].id}/intro"

    rows = (
        await db_session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.meeting_id == made["meeting"].id,
                AttendanceRecord.user_id == test_student.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].source == "qr"
    assert rows[0].status == "present"


# ----- idempotency: single-use per student -----

@pytest.mark.asyncio
async def test_scan_is_idempotent_no_duplicate_row(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    made = await _setup(db_session, test_instructor, test_student)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    async with _student_client(db_session, test_student) as ac:
        r1 = await ac.post(f"/api/attend/{launch.token}")
        r2 = await ac.post(f"/api/attend/{launch.token}")
    app.dependency_overrides.clear()

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["data"]["attendance_id"] == r2.json()["data"]["attendance_id"]

    rows = (
        await db_session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.meeting_id == made["meeting"].id,
                AttendanceRecord.user_id == test_student.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_second_scan_does_not_downgrade_status(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    """First scan wins: a present check-in stays present even if a later scan
    would derive late (single-use, ``on_conflict_do_nothing``)."""
    made = await _setup(db_session, test_instructor, test_student)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    async with _student_client(db_session, test_student) as ac:
        r1 = await ac.post(f"/api/attend/{launch.token}")
        # Move the checkpoint window into the past — a fresh derivation would be
        # "late" — then re-scan; the row must NOT change.
        made["cp"].close_at = _utcnow() - timedelta(minutes=1)
        await db_session.commit()
        r2 = await ac.post(f"/api/attend/{launch.token}")
    app.dependency_overrides.clear()

    assert r1.json()["data"]["status"] == "present"
    assert r2.json()["data"]["status"] == "present"


# ----- late derivation -----

@pytest.mark.asyncio
async def test_scan_records_late_when_past_close(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    """A scan past the checkpoint's ``close_at`` while the launch row is still
    active + the token still decodable records ``late`` (mirrors the
    checkpoint-response late derivation)."""
    made = await _setup(
        db_session,
        test_instructor,
        test_student,
        close_at=_utcnow() - timedelta(minutes=5),
    )
    cp = made["cp"]
    now = _utcnow()
    jti = uuid.uuid4().hex
    token = encode_launch_token(
        {
            "launch_id": str(uuid.uuid4()),
            "checkpoint_id": str(cp.id),
            "meeting_id": str(cp.meeting_id),
            "jti": jti,
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
    )
    db_session.add(
        CheckpointLaunch(
            checkpoint_id=cp.id,
            meeting_id=cp.meeting_id,
            token=token,
            jti=jti,
            window_start=now - timedelta(hours=1),
            window_end=now + timedelta(hours=1),
            launched_by=test_instructor.id,
            status="active",
        )
    )
    await db_session.commit()

    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{token}")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "late"


# ----- typed 4xx failures -----

@pytest.mark.asyncio
async def test_scan_tampered_token_rejected(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    made = await _setup(db_session, test_instructor, test_student)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    tampered = launch.token[:-1] + ("A" if launch.token[-1] != "A" else "B")
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{tampered}")
    app.dependency_overrides.clear()

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "LAUNCH_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_scan_expired_token_rejected(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    made = await _setup(db_session, test_instructor, test_student)
    cp = made["cp"]
    token = encode_launch_token(
        {
            "launch_id": str(uuid.uuid4()),
            "checkpoint_id": str(cp.id),
            "meeting_id": str(cp.meeting_id),
            "jti": uuid.uuid4().hex,
            "exp": int((_utcnow() - timedelta(minutes=5)).timestamp()),
        }
    )
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{token}")
    app.dependency_overrides.clear()

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "LAUNCH_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_scan_closed_launch_rejected(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    """A valid token whose launch row was rotated/closed → typed 409."""
    made = await _setup(db_session, test_instructor, test_student)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    token = launch.token
    launch.status = "closed"
    await db_session.commit()

    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{token}")
    app.dependency_overrides.clear()

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "LAUNCH_CLOSED"


@pytest.mark.asyncio
async def test_scan_unknown_launch_rejected(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    """A well-signed token whose ``jti`` has no launch row → typed 409."""
    made = await _setup(db_session, test_instructor, test_student)
    cp = made["cp"]
    token = encode_launch_token(
        {
            "launch_id": str(uuid.uuid4()),
            "checkpoint_id": str(cp.id),
            "meeting_id": str(cp.meeting_id),
            "jti": uuid.uuid4().hex,  # no matching row
            "exp": int((_utcnow() + timedelta(hours=1)).timestamp()),
        }
    )
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{token}")
    app.dependency_overrides.clear()

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "LAUNCH_CLOSED"


@pytest.mark.asyncio
async def test_scan_requires_active_enrollment(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    made = await _setup(db_session, test_instructor, test_student, enroll=False)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{launch.token}")
    app.dependency_overrides.clear()

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_scan_rejects_non_student(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    made = await _setup(db_session, test_instructor, test_student)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    # Authenticate as the instructor — the scan surface is student-only.
    async with _student_client(db_session, test_instructor) as ac:
        r = await ac.post(f"/api/attend/{launch.token}")
    app.dependency_overrides.clear()

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_scan_does_not_emit_mastery_or_learning_event(
    db_session: AsyncSession, test_instructor: User, test_student: User, launch_secret
):
    """Attendance is participation ONLY — no mastery Task / learning_event."""
    from app.models.task import Task

    made = await _setup(db_session, test_instructor, test_student)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/attend/{launch.token}")
    app.dependency_overrides.clear()
    assert r.status_code == 200, r.text

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    assert tasks == []
