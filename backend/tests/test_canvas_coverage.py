"""Targeted tests to lift coverage on Canvas modules over 80%.

These focus on uncovered branches that the primary flow tests do not
exercise: OAuth HTTP calls, pagination, scheduler loop control flow,
file-type fallbacks, and error-path API responses.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.models import (
    CanvasIntegration,
    CanvasSyncEvent,
    CanvasUserCredential,
    Enrollment,
    User,
)
from app.models.course import Course
from app.services import (
    canvas_client as canvas_client_svc,
)
from app.services import canvas_files, canvas_oauth, canvas_sync
from app.services.crypto import encrypt_secret


# --------------------------------------------------------------------------
# canvas_oauth.exchange_code / refresh_access_token
# --------------------------------------------------------------------------


class _StubAsyncClient:
    """Minimal stand-in for httpx.AsyncClient used by canvas_oauth."""

    def __init__(self, response_json: dict, *, status_code: int = 200) -> None:
        self._response = httpx.Response(
            status_code=status_code,
            json=response_json,
            request=httpx.Request("POST", "https://canvas.ust.hk/login/oauth2/token"),
        )
        self.posted: list[tuple[str, dict]] = []

    async def __aenter__(self) -> "_StubAsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:  # noqa: ANN001
        return None

    async def post(self, url: str, data: dict) -> httpx.Response:
        self.posted.append((url, data))
        return self._response


@pytest.mark.asyncio
async def test_exchange_code_hits_token_endpoint(monkeypatch):
    """exchange_code POSTs to /login/oauth2/token with authorization_code grant."""
    monkeypatch.setattr(canvas_oauth.settings, "canvas_base_url", "https://canvas.ust.hk")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_client_id", "cid")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_client_secret", "csec")
    monkeypatch.setattr(
        canvas_oauth.settings, "canvas_redirect_uri", "https://api/cb"
    )

    stub = _StubAsyncClient({"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    monkeypatch.setattr(
        canvas_oauth.httpx, "AsyncClient", lambda **_: stub
    )

    result = await canvas_oauth.exchange_code("the-code")

    assert result["access_token"] == "at"
    (url, data) = stub.posted[0]
    assert url.endswith("/login/oauth2/token")
    assert data["grant_type"] == "authorization_code"
    assert data["code"] == "the-code"
    assert data["client_id"] == "cid"
    assert data["client_secret"] == "csec"


@pytest.mark.asyncio
async def test_refresh_access_token_hits_token_endpoint(monkeypatch):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_base_url", "https://canvas.ust.hk")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_client_id", "cid")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_client_secret", "csec")

    stub = _StubAsyncClient({"access_token": "fresh", "expires_in": 3600})
    monkeypatch.setattr(canvas_oauth.httpx, "AsyncClient", lambda **_: stub)

    result = await canvas_oauth.refresh_access_token("old-refresh")

    assert result["access_token"] == "fresh"
    (_, data) = stub.posted[0]
    assert data["grant_type"] == "refresh_token"
    assert data["refresh_token"] == "old-refresh"


# --------------------------------------------------------------------------
# CanvasClient: pagination and thin REST wrappers
# --------------------------------------------------------------------------


def _make_cred(user_id) -> CanvasUserCredential:
    return CanvasUserCredential(
        user_id=user_id,
        canvas_base_url="https://canvas.ust.hk",
        canvas_user_id="1",
        access_token_encrypted=encrypt_secret("at"),
        refresh_token_encrypted=encrypt_secret("rt"),
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes="x",
        status="active",
    )


@pytest.mark.asyncio
async def test_client_paginate_follows_link_header(db_session, logged_in_user):
    cred = _make_cred(logged_in_user.id)
    db_session.add(cred)
    await db_session.commit()

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First page — signal a "next" page via Link header.
            return httpx.Response(
                200,
                json=[{"id": 1}, {"id": 2}],
                headers={
                    "Link": (
                        '<https://canvas.ust.hk/api/v1/courses/9/enrollments'
                        '?page=2&per_page=50>; rel="next"'
                    )
                },
            )
        # Second page — no Link header terminates pagination.
        return httpx.Response(200, json=[{"id": 3}])

    transport = httpx.MockTransport(handler)
    client = await canvas_client_svc.get_client_for_user(
        db_session, logged_in_user.id, transport=transport
    )
    rows = await client.list_course_enrollments("9")
    assert [r["id"] for r in rows] == [1, 2, 3]
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_client_thin_methods_dispatch(db_session, logged_in_user):
    """Exercise list_my_courses, get_course, list_course_files, get_file."""
    cred = _make_cred(logged_in_user.id)
    db_session.add(cred)
    await db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/users/self/courses"):
            return httpx.Response(200, json=[{"id": 1, "name": "C1"}])
        if path.endswith("/courses/9"):
            return httpx.Response(200, json={"id": 9, "name": "Physics"})
        if path.endswith("/courses/9/files"):
            return httpx.Response(200, json=[{"id": 77}])
        if path.endswith("/files/77"):
            return httpx.Response(
                200, json={"id": 77, "url": "https://cdn/f", "display_name": "x"}
            )
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    client = await canvas_client_svc.get_client_for_user(
        db_session, logged_in_user.id, transport=transport
    )

    my = await client.list_my_courses("teacher")
    course = await client.get_course("9")
    files = await client.list_course_files("9")
    meta = await client.get_file("77")
    assert my[0]["id"] == 1
    assert course["name"] == "Physics"
    assert files[0]["id"] == 77
    assert meta["display_name"] == "x"


@pytest.mark.asyncio
async def test_client_download_file_returns_bytes(db_session, logged_in_user, monkeypatch):
    cred = _make_cred(logged_in_user.id)
    db_session.add(cred)
    await db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"the-bytes")

    transport = httpx.MockTransport(handler)
    client = await canvas_client_svc.get_client_for_user(
        db_session, logged_in_user.id, transport=transport
    )
    monkeypatch.setattr(canvas_client_svc.settings, "canvas_allowed_hosts", "cdn")
    body = await client.download_file("https://cdn/signed")
    assert body == b"the-bytes"


# --------------------------------------------------------------------------
# canvas_files._derive_file_type
# --------------------------------------------------------------------------


def test_derive_file_type_known_content_types():
    assert canvas_files._derive_file_type("application/pdf", "x.pdf") == "pdf"
    assert canvas_files._derive_file_type("audio/x-m4a", "y.m4a") == "m4a"


def test_derive_file_type_falls_back_to_extension():
    assert (
        canvas_files._derive_file_type("application/octet-stream", "notes.md")
        == "md"
    )


def test_derive_file_type_falls_back_to_content_type_prefix():
    # No extension and unknown content type → split on /.
    assert (
        canvas_files._derive_file_type("application/weird", "noext") == "application"
    )


def test_derive_file_type_final_fallback_bin():
    assert canvas_files._derive_file_type("garbage", "noext") == "bin"


# --------------------------------------------------------------------------
# canvas_sync: error and scheduler paths
# --------------------------------------------------------------------------


async def _seed_active_integration(db_session) -> tuple[User, Course, CanvasIntegration]:
    instructor = User(
        better_auth_id="dev_cov_inst",
        email="cov-inst@ust.hk",
        full_name="Cov",
        role="instructor",
    )
    db_session.add(instructor)
    await db_session.flush()
    db_session.add(
        CanvasUserCredential(
            user_id=instructor.id,
            canvas_base_url="https://canvas.ust.hk",
            canvas_user_id="7",
            access_token_encrypted=encrypt_secret("at"),
            refresh_token_encrypted=encrypt_secret("rt"),
            access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes="x",
            status="active",
        )
    )
    course = Course(
        name="Cov Course",
        language="english",
        instructor_id=instructor.id,
        enroll_code="COV00001",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=instructor.id, role="instructor")
    )
    integration = CanvasIntegration(
        course_id=course.id,
        connected_by_user_id=instructor.id,
        canvas_course_id="333",
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
async def test_sync_reauth_required_logs_error_event(db_session, monkeypatch):
    _, course, integration = await _seed_active_integration(db_session)

    async def reauth_raises(db, user_id, transport=None):
        raise canvas_client_svc.CanvasReauthRequired()

    monkeypatch.setattr(canvas_client_svc, "get_client_for_user", reauth_raises)

    await canvas_sync.sync_integration(db_session, integration)

    event = (
        await db_session.execute(
            select(CanvasSyncEvent).where(
                CanvasSyncEvent.course_id == course.id,
                CanvasSyncEvent.event_type == "error",
            )
        )
    ).scalar_one()
    assert event.payload == {"code": "canvas_reauth_required"}
    # Status is NOT flipped on reauth (user-fixable).
    await db_session.refresh(integration)
    assert integration.sync_status == "active"


@pytest.mark.asyncio
async def test_sync_logs_error_when_roster_fetch_fails(db_session, monkeypatch):
    _, course, _integration = await _seed_active_integration(db_session)

    async def boom_enrollments(self, cid):
        raise RuntimeError("canvas 500")

    # Files still succeed so we also exercise the success branch for file_scan.
    async def ok_files(self, cid):
        return []

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient,
        "list_course_enrollments",
        boom_enrollments,
    )
    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_files", ok_files
    )

    await canvas_sync.sync_integration(db_session, _integration)

    errors = (
        await db_session.execute(
            select(CanvasSyncEvent).where(
                CanvasSyncEvent.course_id == course.id,
                CanvasSyncEvent.event_type == "error",
            )
        )
    ).scalars().all()
    stages = {e.payload.get("stage") for e in errors}
    assert "roster_diff" in stages


@pytest.mark.asyncio
async def test_sync_logs_error_when_file_scan_fails(db_session, monkeypatch):
    _, course, integration = await _seed_active_integration(db_session)

    async def ok_enrollments(self, cid):
        return []

    async def boom_files(self, cid):
        raise RuntimeError("canvas files 500")

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient,
        "list_course_enrollments",
        ok_enrollments,
    )
    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_files", boom_files
    )

    await canvas_sync.sync_integration(db_session, integration)

    errors = (
        await db_session.execute(
            select(CanvasSyncEvent).where(
                CanvasSyncEvent.course_id == course.id,
                CanvasSyncEvent.event_type == "error",
            )
        )
    ).scalars().all()
    stages = {e.payload.get("stage") for e in errors}
    assert "file_scan" in stages


@pytest.mark.asyncio
async def test_due_integrations_filters_by_last_sync(db_session):
    _, _, integration = await _seed_active_integration(db_session)

    # No last_roster_sync_at → due.
    due = await canvas_sync._due_integrations(db_session)
    assert any(i.id == integration.id for i in due)

    # Mark as just-synced → no longer due.
    integration.last_roster_sync_at = datetime.now(timezone.utc)
    await db_session.commit()
    due = await canvas_sync._due_integrations(db_session)
    assert not any(i.id == integration.id for i in due)

    # Disconnected integrations are excluded regardless of sync recency.
    integration.sync_status = "disconnected"
    integration.last_roster_sync_at = None
    await db_session.commit()
    due = await canvas_sync._due_integrations(db_session)
    assert not any(i.id == integration.id for i in due)


@pytest.mark.asyncio
async def test_run_scheduler_exits_on_shutdown_event(monkeypatch):
    """run_scheduler must return cleanly when the shutdown event is set."""
    # Short-circuit: no due integrations so the inner loop is effectively a no-op.
    async def no_due(session):
        return []

    monkeypatch.setattr(canvas_sync, "_due_integrations", no_due)
    # Collapse the poll interval so the wait_for returns immediately.
    monkeypatch.setattr(canvas_sync, "SCHEDULER_POLL_SECONDS", 0.01)

    shutdown = asyncio.Event()
    shutdown.set()
    # With shutdown already set, wait_for returns and the loop returns.
    await asyncio.wait_for(canvas_sync.run_scheduler(shutdown), timeout=2.0)


# --------------------------------------------------------------------------
# canvas.py API: 404 branches (no CanvasIntegration) for import/roster/sync.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_404_when_not_connected(async_client, logged_in_user, db_session):
    course = Course(
        name="Orphan",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="ORPHAN01",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()

    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/files/import", json={"file_ids": ["1"]}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_roster_404_when_not_connected(async_client, logged_in_user, db_session):
    course = Course(
        name="Orphan2",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="ORPHAN02",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()

    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/roster/import",
        json={"send_invite_emails": False},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_manual_sync_404_when_not_connected(
    async_client, logged_in_user, db_session
):
    course = Course(
        name="Orphan3",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="ORPHAN03",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()

    resp = await async_client.post(f"/api/courses/{course.id}/canvas/sync")
    assert resp.status_code == 404
