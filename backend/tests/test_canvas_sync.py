"""Tests for the daily Canvas sync service (roster diff + file scan)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    CanvasIntegration,
    CanvasSyncEvent,
    CanvasUserCredential,
    Course,
    Enrollment,
    User,
)
from app.services import canvas_client as canvas_client_svc
from app.services import canvas_sync
from app.services.crypto import encrypt_secret


async def _seed_active_integration(
    db_session, *, canvas_course_id: str = "888"
) -> tuple[User, Course, CanvasIntegration]:
    instructor = User(
        better_auth_id="dev_sync_inst",
        email="sync-inst@ust.hk",
        full_name="Inst",
        role="instructor",
    )
    db_session.add(instructor)
    await db_session.flush()
    db_session.add(
        CanvasUserCredential(
            user_id=instructor.id,
            canvas_base_url="https://canvas.ust.hk",
            canvas_user_id="42",
            access_token_encrypted=encrypt_secret("at"),
            refresh_token_encrypted=encrypt_secret("rt"),
            access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes="x",
            status="active",
        )
    )
    course = Course(
        name="Sync Course",
        language="english",
        instructor_id=instructor.id,
        enroll_code="SYNC0001",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=instructor.id, role="instructor")
    )
    integration = CanvasIntegration(
        course_id=course.id,
        connected_by_user_id=instructor.id,
        canvas_course_id=canvas_course_id,
        canvas_base_url="https://canvas.ust.hk",
        sync_status="active",
    )
    db_session.add(integration)
    await db_session.commit()
    await db_session.refresh(integration)
    await db_session.refresh(course)
    await db_session.refresh(instructor)
    return instructor, course, integration


@pytest.mark.asyncio
async def test_claim_due_integration_skips_locked_rows(db_session):
    """A second ``_claim_due_integration`` call in another session
    must skip the row that the first session already holds a FOR UPDATE
    lock on, falling through to the next due integration.

    Regression: the old ``_due_integrations`` query had no row locking,
    so concurrent workers could both pick the same integration before
    either finished syncing, producing duplicate sync events and
    enrollment unique-constraint races.
    """
    from tests.conftest import test_session_factory

    _, _, integration_a = await _seed_active_integration(
        db_session, canvas_course_id="111"
    )
    instructor_b = User(
        better_auth_id="dev_sync_inst_b",
        email="sync-b@ust.hk",
        full_name="B",
        role="instructor",
    )
    db_session.add(instructor_b)
    await db_session.flush()
    course_b = Course(
        name="Sync B",
        language="english",
        instructor_id=instructor_b.id,
        enroll_code="SYNC-B",
    )
    db_session.add(course_b)
    await db_session.flush()
    integration_b = CanvasIntegration(
        course_id=course_b.id,
        connected_by_user_id=instructor_b.id,
        canvas_course_id="222",
        canvas_base_url="https://canvas.ust.hk",
        sync_status="active",
    )
    db_session.add(integration_b)
    await db_session.commit()

    # Hold a FOR UPDATE lock on integration_a in session A, then call
    # _claim_due_integration in a fresh session B. SKIP LOCKED must hop
    # past the locked row and return integration_b.
    async with test_session_factory() as session_a:
        first_claim = await canvas_sync._claim_due_integration(session_a)
        assert first_claim is not None
        a_id = first_claim.id

        async with test_session_factory() as session_b:
            second_claim = await canvas_sync._claim_due_integration(session_b)

        assert second_claim is not None
        assert second_claim.id != a_id

    # And the in-memory ``exclude`` set must keep us from re-claiming an
    # already-processed integration in the same scheduler pass.
    async with test_session_factory() as session_c:
        excluded = await canvas_sync._claim_due_integration(
            session_c, exclude={integration_a.id, integration_b.id}
        )
    assert excluded is None


@pytest.mark.asyncio
async def test_sync_writes_roster_diff_and_file_scan_events(
    db_session, monkeypatch
):
    instructor, course, integration = await _seed_active_integration(db_session)

    async def fake_enrollments(self, cid):
        # Empty roster — no students. Instructor should be preserved.
        return []

    async def fake_files(self, cid):
        return [{"id": 1, "display_name": "lecture.pdf"}]

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient,
        "list_course_enrollments",
        fake_enrollments,
    )
    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_files", fake_files
    )

    await canvas_sync.sync_integration(db_session, integration)

    events = (
        await db_session.execute(
            select(CanvasSyncEvent).where(
                CanvasSyncEvent.course_id == course.id
            )
        )
    ).scalars().all()
    types = {e.event_type for e in events}
    assert "roster_diff" in types
    assert "file_scan" in types

    file_scan = next(e for e in events if e.event_type == "file_scan")
    assert file_scan.payload["canvas_total"] == 1
    assert file_scan.payload["new_available"] == 1

    await db_session.refresh(integration)
    assert integration.last_roster_sync_at is not None
    assert integration.last_file_scan_at is not None


@pytest.mark.asyncio
async def test_sync_preserves_connected_instructor(db_session, monkeypatch):
    """Instructor who linked the course must not be dropped when Canvas
    omits them from the enrollment list."""
    instructor, course, integration = await _seed_active_integration(db_session)

    async def fake_enrollments(self, cid):
        return []  # Canvas returns nobody — including the instructor.

    async def fake_files(self, cid):
        return []

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient,
        "list_course_enrollments",
        fake_enrollments,
    )
    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_files", fake_files
    )

    await canvas_sync.sync_integration(db_session, integration)

    enr = (
        await db_session.execute(
            select(Enrollment).where(
                Enrollment.course_id == course.id,
                Enrollment.user_id == instructor.id,
            )
        )
    ).scalar_one_or_none()
    assert enr is not None, "Instructor enrollment was dropped by sync"

    roster_event = (
        await db_session.execute(
            select(CanvasSyncEvent).where(
                CanvasSyncEvent.course_id == course.id,
                CanvasSyncEvent.event_type == "roster_diff",
            )
        )
    ).scalar_one()
    assert roster_event.payload["dropped"] == 0


@pytest.mark.asyncio
async def test_sync_marks_disconnected_when_credential_missing(
    db_session, monkeypatch
):
    instructor, course, integration = await _seed_active_integration(db_session)

    # Wipe the instructor's credential — simulates them disconnecting Canvas.
    cred = (
        await db_session.execute(
            select(CanvasUserCredential).where(
                CanvasUserCredential.user_id == instructor.id
            )
        )
    ).scalar_one()
    await db_session.delete(cred)
    await db_session.commit()

    await canvas_sync.sync_integration(db_session, integration)

    await db_session.refresh(integration)
    assert integration.sync_status == "disconnected"


@pytest.mark.asyncio
async def test_manual_sync_triggers_events(
    async_client, logged_in_user, linked_course_fixture, db_session, monkeypatch
):
    """POST /api/courses/{id}/canvas/sync runs a sync and writes events;
    GET /api/courses/{id}/canvas/sync-events returns them newest-first."""
    course = linked_course_fixture["meli_course"]

    async def fake_enrollments(self, cid):
        return [
            {
                "user_id": 200,
                "type": "StudentEnrollment",
                "user": {"email": "newstu@connect.ust.hk", "name": "New Stu"},
            }
        ]

    async def fake_files(self, cid):
        return [{"id": 7, "display_name": "slides.pdf"}]

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient,
        "list_course_enrollments",
        fake_enrollments,
    )
    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_files", fake_files
    )

    resp = await async_client.post(f"/api/courses/{course.id}/canvas/sync")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["sync_status"] == "active"
    assert data["last_roster_sync_at"] is not None
    assert data["last_file_scan_at"] is not None

    events_resp = await async_client.get(
        f"/api/courses/{course.id}/canvas/sync-events?limit=20"
    )
    assert events_resp.status_code == 200, events_resp.text
    events = events_resp.json()["data"]
    types = {e["event_type"] for e in events}
    assert "roster_diff" in types
    assert "file_scan" in types

    # Newest-first ordering: created_at descending.
    timestamps = [e["created_at"] for e in events]
    assert timestamps == sorted(timestamps, reverse=True)
