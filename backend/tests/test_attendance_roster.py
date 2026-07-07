"""P3 T11 — attendance roster result + manual override.

Two teacher-facing, owner-guarded surfaces:

* ``GET /api/meetings/{id}/attendance`` — the roster for a meeting's course.
  Each active-enrolled *student* is reported present|late|excused|absent.
  ``absent`` is DERIVED: an active-enrolled student with NO
  ``attendance_records`` row for that meeting is absent. Non-owner → 404.

* ``PATCH /api/attendance/{id}`` — manual override. Sets ``status`` +
  a REQUIRED ``override_reason``, stamps ``override_by`` = current user and
  ``source='manual_override'``, and appends an append-only audit entry
  (mirrors the T5 ``_append_review_action`` shape). Non-owner → 404; a missing
  reason is a 422 at the schema boundary.

Attendance is participation ONLY — an override NEVER emits mastery / a
learning_event.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models.attendance import AttendanceRecord
from app.models.course import Course, Enrollment
from app.models.curriculum import CourseMeeting
from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _make_student(db: AsyncSession, suffix: str) -> User:
    user = User(
        better_auth_id=f"dev_student_{suffix}",
        email=f"student_{suffix}@connect.ust.hk",
        full_name=f"Student {suffix}",
        role="student",
    )
    db.add(user)
    await db.flush()
    return user


async def _setup(
    db: AsyncSession,
    instructor: User,
    *,
    n_students: int = 3,
) -> dict:
    course = Course(
        name="Roster Course",
        language="zh",
        instructor_id=instructor.id,
        enroll_code="RC" + uuid.uuid4().hex[:6].upper(),
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

    students: list[User] = []
    for i in range(n_students):
        s = await _make_student(db, f"{uuid.uuid4().hex[:8]}_{i}")
        students.append(s)
        db.add(
            Enrollment(
                course_id=course.id,
                user_id=s.id,
                role="student",
                status="active",
            )
        )
    await db.flush()
    await db.commit()
    return {"course": course, "meeting": meeting, "students": students}


async def _add_record(
    db: AsyncSession,
    meeting: CourseMeeting,
    student: User,
    *,
    status: str = "present",
    source: str = "qr",
) -> AttendanceRecord:
    rec = AttendanceRecord(
        meeting_id=meeting.id,
        user_id=student.id,
        status=status,
        source=source,
        checked_in_at=_utcnow(),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


def _client(db_session: AsyncSession, user: User) -> AsyncClient:
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


# ----- roster GET -----

@pytest.mark.asyncio
async def test_roster_derives_absent_for_unscanned(
    db_session: AsyncSession, test_instructor: User
):
    made = await _setup(db_session, test_instructor, n_students=3)
    students = made["students"]
    # Only the first two scan; student[2] is derived-absent.
    await _add_record(db_session, made["meeting"], students[0], status="present")
    await _add_record(db_session, made["meeting"], students[1], status="late")

    async with _client(db_session, test_instructor) as ac:
        r = await ac.get(f"/api/meetings/{made['meeting'].id}/attendance")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["meeting_id"] == str(made["meeting"].id)
    assert data["course_id"] == str(made["course"].id)
    assert data["present_count"] == 1
    assert data["late_count"] == 1
    assert data["absent_count"] == 1
    assert data["excused_count"] == 0

    by_user = {e["user_id"]: e for e in data["entries"]}
    assert by_user[str(students[0].id)]["status"] == "present"
    assert by_user[str(students[0].id)]["source"] == "qr"
    assert by_user[str(students[1].id)]["status"] == "late"
    # Derived-absent: no row, so no attendance_id / source.
    absent = by_user[str(students[2].id)]
    assert absent["status"] == "absent"
    assert absent["attendance_id"] is None
    assert absent["source"] is None


@pytest.mark.asyncio
async def test_roster_excludes_instructor_and_pending(
    db_session: AsyncSession, test_instructor: User
):
    made = await _setup(db_session, test_instructor, n_students=1)
    course = made["course"]
    # Instructor enrollment + a pending student must NOT appear in the roster.
    db_session.add(
        Enrollment(
            course_id=course.id,
            user_id=test_instructor.id,
            role="instructor",
            status="active",
        )
    )
    pending = await _make_student(db_session, f"pending_{uuid.uuid4().hex[:8]}")
    db_session.add(
        Enrollment(
            course_id=course.id,
            user_id=pending.id,
            role="student",
            status="pending",
        )
    )
    await db_session.commit()

    async with _client(db_session, test_instructor) as ac:
        r = await ac.get(f"/api/meetings/{made['meeting'].id}/attendance")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    user_ids = {e["user_id"] for e in data["entries"]}
    assert str(test_instructor.id) not in user_ids
    assert str(pending.id) not in user_ids
    assert len(data["entries"]) == 1  # only the single active student


@pytest.mark.asyncio
async def test_roster_owner_guarded_404_for_non_owner(
    db_session: AsyncSession, test_instructor: User
):
    made = await _setup(db_session, test_instructor, n_students=1)
    other = User(
        better_auth_id="dev_other_instr",
        email="other@ust.hk",
        full_name="Other Instructor",
        role="instructor",
    )
    db_session.add(other)
    await db_session.commit()

    async with _client(db_session, other) as ac:
        r = await ac.get(f"/api/meetings/{made['meeting'].id}/attendance")
    app.dependency_overrides.clear()

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_roster_rejects_student(
    db_session: AsyncSession, test_instructor: User, test_student: User
):
    made = await _setup(db_session, test_instructor, n_students=1)
    async with _client(db_session, test_student) as ac:
        r = await ac.get(f"/api/meetings/{made['meeting'].id}/attendance")
    app.dependency_overrides.clear()
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_roster_unknown_meeting_404(
    db_session: AsyncSession, test_instructor: User
):
    async with _client(db_session, test_instructor) as ac:
        r = await ac.get(f"/api/meetings/{uuid.uuid4()}/attendance")
    app.dependency_overrides.clear()
    assert r.status_code == 404


# ----- PATCH override -----

@pytest.mark.asyncio
async def test_override_sets_status_source_and_reason(
    db_session: AsyncSession, test_instructor: User
):
    made = await _setup(db_session, test_instructor, n_students=1)
    student = made["students"][0]
    rec = await _add_record(
        db_session, made["meeting"], student, status="present", source="qr"
    )

    async with _client(db_session, test_instructor) as ac:
        r = await ac.patch(
            f"/api/attendance/{rec.id}",
            json={"status": "excused", "override_reason": "Doctor's note"},
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "excused"
    assert data["source"] == "manual_override"
    assert data["override_reason"] == "Doctor's note"
    assert data["override_by"] == str(test_instructor.id)

    await db_session.refresh(rec)
    assert rec.status == "excused"
    assert rec.source == "manual_override"
    assert rec.override_reason == "Doctor's note"
    assert rec.override_by == test_instructor.id


@pytest.mark.asyncio
async def test_override_appends_audit_entry(
    db_session: AsyncSession, test_instructor: User
):
    made = await _setup(db_session, test_instructor, n_students=1)
    student = made["students"][0]
    rec = await _add_record(
        db_session, made["meeting"], student, status="absent", source="qr"
    )

    async with _client(db_session, test_instructor) as ac:
        r = await ac.patch(
            f"/api/attendance/{rec.id}",
            json={"status": "present", "override_reason": "Was here, forgot to scan"},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 200, r.text

    meeting = await db_session.get(CourseMeeting, made["meeting"].id)
    await db_session.refresh(meeting)
    actions = (meeting.post_meeting_summary or {}).get("review_actions", [])
    assert len(actions) == 1
    entry = actions[0]
    assert entry["action"] == "attendance_override"
    assert entry["from"] == "absent"
    assert entry["to"] == "present"
    assert entry["reason"] == "Was here, forgot to scan"
    assert entry["actor_id"] == str(test_instructor.id)
    assert entry["attendance_id"] == str(rec.id)


@pytest.mark.asyncio
async def test_override_requires_reason(
    db_session: AsyncSession, test_instructor: User
):
    made = await _setup(db_session, test_instructor, n_students=1)
    rec = await _add_record(db_session, made["meeting"], made["students"][0])

    async with _client(db_session, test_instructor) as ac:
        missing = await ac.patch(
            f"/api/attendance/{rec.id}", json={"status": "excused"}
        )
        blank = await ac.patch(
            f"/api/attendance/{rec.id}",
            json={"status": "excused", "override_reason": ""},
        )
    app.dependency_overrides.clear()

    assert missing.status_code == 422
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_override_invalid_status_422(
    db_session: AsyncSession, test_instructor: User
):
    made = await _setup(db_session, test_instructor, n_students=1)
    rec = await _add_record(db_session, made["meeting"], made["students"][0])

    async with _client(db_session, test_instructor) as ac:
        r = await ac.patch(
            f"/api/attendance/{rec.id}",
            json={"status": "here", "override_reason": "x"},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_override_owner_guarded_404(
    db_session: AsyncSession, test_instructor: User
):
    made = await _setup(db_session, test_instructor, n_students=1)
    rec = await _add_record(db_session, made["meeting"], made["students"][0])
    other = User(
        better_auth_id="dev_other_instr2",
        email="other2@ust.hk",
        full_name="Other Instructor",
        role="instructor",
    )
    db_session.add(other)
    await db_session.commit()

    async with _client(db_session, other) as ac:
        r = await ac.patch(
            f"/api/attendance/{rec.id}",
            json={"status": "excused", "override_reason": "x"},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_override_unknown_record_404(
    db_session: AsyncSession, test_instructor: User
):
    async with _client(db_session, test_instructor) as ac:
        r = await ac.patch(
            f"/api/attendance/{uuid.uuid4()}",
            json={"status": "excused", "override_reason": "x"},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_override_rejects_student(
    db_session: AsyncSession, test_instructor: User, test_student: User
):
    made = await _setup(db_session, test_instructor, n_students=1)
    rec = await _add_record(db_session, made["meeting"], made["students"][0])
    async with _client(db_session, test_student) as ac:
        r = await ac.patch(
            f"/api/attendance/{rec.id}",
            json={"status": "excused", "override_reason": "x"},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_override_does_not_emit_mastery_or_learning_event(
    db_session: AsyncSession, test_instructor: User
):
    from app.models.task import Task

    made = await _setup(db_session, test_instructor, n_students=1)
    rec = await _add_record(db_session, made["meeting"], made["students"][0])

    async with _client(db_session, test_instructor) as ac:
        r = await ac.patch(
            f"/api/attendance/{rec.id}",
            json={"status": "excused", "override_reason": "x"},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 200, r.text

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    assert tasks == []
