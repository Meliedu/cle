"""Tests for the weekly ``draft_report`` cron + end-term fan-out (P7 B4).

``_body_draft_reports`` mirrors ``_body_alerts_enqueue``: it fans out ONE
``draft_report`` task per non-deleted course per *active* student for the
current weekly window, gated by ``pilot.report_cadence.weekly``. The fan-out is
deduped so a burst can't pile up — at most one PENDING ``draft_report`` task per
``(course, user, period)``. Drafting stays OFF the request path: the owner
endpoint ``POST /courses/{id}/reports/draft?period=end_term`` only *enqueues*.

The task payload matches B3's ``run_draft_report`` shape:
``{course_id, audience, period, user_id?, period_start, period_end}``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

import app.pilot as pilot_module
from app.models.course import Course, Enrollment
from app.models.task import Task
from app.pilot import get_pilot_profile
from app.pilot.base import ReportCadence
from app.services import worker as worker_module
from tests.conftest import test_session_factory


@pytest_asyncio.fixture(autouse=True)
async def _redirect_cron_to_test_db(monkeypatch, db_session):
    """Point the cron body's session factory at the test database so its writes
    are visible to the test's ``db_session`` (mirrors test_cron_watermarks)."""
    monkeypatch.setattr(
        worker_module, "async_session_factory", test_session_factory
    )
    yield


async def _make_student(db_session, suffix: str):
    from app.models.user import User

    user = User(
        better_auth_id=f"dev_student_{suffix}",
        email=f"student_{suffix}@connect.ust.hk",
        full_name=f"Student {suffix}",
        role="student",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_course(db_session, instructor, name: str):
    course = Course(
        name=name,
        language="zh",
        instructor_id=instructor.id,
        enroll_code="RPT" + uuid.uuid4().hex[:5].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _enroll(db_session, course, user, *, role="student", status="active"):
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=user.id, role=role, status=status
        )
    )
    await db_session.commit()


async def _pending_draft_tasks(db_session):
    return (
        await db_session.execute(
            select(Task).where(
                Task.task_type == "draft_report",
                Task.status == "pending",
            )
        )
    ).scalars().all()


@pytest.mark.asyncio
async def test_fans_out_per_course_per_active_student(
    db_session, test_instructor
):
    """One weekly draft_report task per (non-deleted course, active student).
    Pending/rejected enrollments and instructor rows never produce a task."""
    course_a = await _make_course(db_session, test_instructor, "LANG1511")
    course_b = await _make_course(db_session, test_instructor, "LANG1512")

    active_1 = await _make_student(db_session, "a1")
    active_2 = await _make_student(db_session, "a2")
    pending = await _make_student(db_session, "p1")

    await _enroll(db_session, course_a, active_1, status="active")
    await _enroll(db_session, course_a, active_2, status="active")
    await _enroll(db_session, course_a, pending, status="pending")
    await _enroll(db_session, course_a, test_instructor, role="instructor")
    await _enroll(db_session, course_b, active_1, status="active")

    now = datetime.now(timezone.utc)
    await worker_module._body_draft_reports(now=now)

    tasks = await _pending_draft_tasks(db_session)
    keys = {
        (t.payload["course_id"], t.payload["user_id"], t.payload["period"])
        for t in tasks
    }
    assert keys == {
        (str(course_a.id), str(active_1.id), "weekly"),
        (str(course_a.id), str(active_2.id), "weekly"),
        (str(course_b.id), str(active_1.id), "weekly"),
    }

    # Payload shape matches B3's run_draft_report contract.
    sample = tasks[0]
    assert sample.payload["audience"] == "student"
    assert sample.payload["period"] == "weekly"
    assert sample.payload["user_id"] is not None
    # Testable window: weekly == last 7 days of the passed-in ``now``.
    assert sample.payload["period_end"] == now.isoformat()
    assert sample.payload["period_start"] == (now - timedelta(days=7)).isoformat()


@pytest.mark.asyncio
async def test_soft_deleted_course_excluded(db_session, test_instructor):
    course = await _make_course(db_session, test_instructor, "LANG1513")
    student = await _make_student(db_session, "sd1")
    await _enroll(db_session, course, student, status="active")
    course.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    await worker_module._body_draft_reports(now=datetime.now(timezone.utc))

    assert await _pending_draft_tasks(db_session) == []


@pytest.mark.asyncio
async def test_dedupes_pending_tasks(db_session, test_instructor):
    """A second cron tick doesn't pile up duplicates — one PENDING task per
    (course, user, period)."""
    course = await _make_course(db_session, test_instructor, "LANG1514")
    student = await _make_student(db_session, "dd1")
    await _enroll(db_session, course, student, status="active")

    now = datetime.now(timezone.utc)
    await worker_module._body_draft_reports(now=now)
    await worker_module._body_draft_reports(now=now + timedelta(hours=1))

    tasks = await _pending_draft_tasks(db_session)
    assert len(tasks) == 1


@pytest.mark.asyncio
async def test_gated_by_report_cadence_weekly(
    db_session, test_instructor, monkeypatch
):
    """When ``pilot.report_cadence.weekly`` is False, nothing is enqueued."""
    course = await _make_course(db_session, test_instructor, "LANG1515")
    student = await _make_student(db_session, "g1")
    await _enroll(db_session, course, student, status="active")

    prof = get_pilot_profile()
    disabled = prof.model_copy(
        update={
            "report_cadence": ReportCadence(
                weekly=False, end_term=prof.report_cadence.end_term
            )
        }
    )
    monkeypatch.setattr(pilot_module, "get_pilot_profile", lambda: disabled)

    await worker_module._body_draft_reports(now=datetime.now(timezone.utc))

    assert await _pending_draft_tasks(db_session) == []


@pytest.mark.asyncio
async def test_registered_weekly_in_cron_ticks(monkeypatch):
    """``_run_cron_ticks`` registers the draft_reports cron on a 7-day cadence
    via ``_claim_and_run_cron`` (CronRun watermark)."""
    calls: list[tuple] = []

    async def fake_claim(name, cadence, body):
        calls.append((name, cadence, body))

    monkeypatch.setattr(worker_module, "_claim_and_run_cron", fake_claim)
    await worker_module._run_cron_ticks()

    entry = [c for c in calls if c[0] == "draft_reports"]
    assert len(entry) == 1
    assert entry[0][1] == timedelta(days=7)
    assert entry[0][2] is worker_module._body_draft_reports


@pytest.mark.asyncio
async def test_end_term_trigger_selects_end_term_period(
    async_client, db_session, logged_in_user
):
    """The owner endpoint enqueues (only) end_term draft_report tasks for the
    course's active students — asserting the PERIOD SELECTION, not wall-clock."""
    course = await _make_course(db_session, logged_in_user, "LANG1511-ET")
    student = await _make_student(db_session, "et1")
    await _enroll(db_session, course, student, status="active")

    resp = await async_client.post(
        f"/api/courses/{course.id}/reports/draft?period=end_term"
    )
    assert resp.status_code == 202

    tasks = await _pending_draft_tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].payload["period"] == "end_term"
    assert tasks[0].payload["audience"] == "student"
    assert tasks[0].payload["user_id"] == str(student.id)
    assert tasks[0].payload["course_id"] == str(course.id)


@pytest.mark.asyncio
async def test_end_term_trigger_rejects_bad_period(
    async_client, db_session, logged_in_user
):
    course = await _make_course(db_session, logged_in_user, "LANG1511-BAD")
    resp = await async_client.post(
        f"/api/courses/{course.id}/reports/draft?period=bogus"
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_end_term_trigger_non_owner_404(
    async_client, db_session, test_instructor
):
    """A course owned by someone else is 404 to the caller (owner guard)."""
    course = await _make_course(db_session, test_instructor, "LANG1511-OTHER")
    resp = await async_client.post(
        f"/api/courses/{course.id}/reports/draft?period=end_term"
    )
    assert resp.status_code == 404
