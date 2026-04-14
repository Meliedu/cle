"""Tests for the per-user CanvasClient and refresh-on-401 behaviour."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.models import CanvasUserCredential
from app.services import canvas_client, canvas_oauth
from app.services.crypto import decrypt_secret, encrypt_secret


@pytest.mark.asyncio
async def test_client_refreshes_on_401(db_session, logged_in_user, monkeypatch):
    cred = CanvasUserCredential(
        user_id=logged_in_user.id,
        canvas_base_url="https://canvas.ust.hk",
        canvas_user_id="1",
        access_token_encrypted=encrypt_secret("stale"),
        refresh_token_encrypted=encrypt_secret("refresh"),
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes="url:GET|/api/v1/users/self",
        status="active",
    )
    db_session.add(cred)
    await db_session.commit()

    refresh_calls = []

    async def fake_refresh(rt):
        refresh_calls.append(rt)
        return {
            "access_token": "fresh",
            "refresh_token": "refresh",
            "expires_in": 3600,
        }

    monkeypatch.setattr(canvas_oauth, "refresh_access_token", fake_refresh)

    call_log = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers["Authorization"].removeprefix("Bearer ")
        call_log.append(token)
        if token == "stale":
            return httpx.Response(401, json={"errors": [{"message": "expired"}]})
        return httpx.Response(200, json={"id": 42, "name": "Alice"})

    transport = httpx.MockTransport(handler)
    client = await canvas_client.get_client_for_user(
        db_session, logged_in_user.id, transport=transport
    )
    result = await client.get_user_self()

    assert result["id"] == 42
    assert call_log == ["stale", "fresh"]
    assert refresh_calls == ["refresh"]

    await db_session.refresh(cred)
    assert decrypt_secret(cred.access_token_encrypted) == "fresh"


@pytest.mark.asyncio
async def test_no_credential_raises(db_session, logged_in_user):
    with pytest.raises(canvas_client.CanvasNotConnected):
        await canvas_client.get_client_for_user(db_session, logged_in_user.id)


@pytest.mark.asyncio
async def test_inactive_credential_raises(db_session, logged_in_user):
    cred = CanvasUserCredential(
        user_id=logged_in_user.id,
        canvas_base_url="https://canvas.ust.hk",
        canvas_user_id="1",
        access_token_encrypted=encrypt_secret("a"),
        refresh_token_encrypted=encrypt_secret("r"),
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes="x",
        status="invalid",
    )
    db_session.add(cred)
    await db_session.commit()
    with pytest.raises(canvas_client.CanvasNotConnected):
        await canvas_client.get_client_for_user(db_session, logged_in_user.id)


@pytest.mark.asyncio
async def test_refresh_failure_marks_invalid(db_session, logged_in_user, monkeypatch):
    cred = CanvasUserCredential(
        user_id=logged_in_user.id,
        canvas_base_url="https://canvas.ust.hk",
        canvas_user_id="1",
        access_token_encrypted=encrypt_secret("stale"),
        refresh_token_encrypted=encrypt_secret("bad-refresh"),
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes="x",
        status="active",
    )
    db_session.add(cred)
    await db_session.commit()

    async def failing_refresh(rt):
        raise httpx.HTTPStatusError(
            "bad", request=httpx.Request("POST", "https://x"),
            response=httpx.Response(400),
        )

    monkeypatch.setattr(canvas_oauth, "refresh_access_token", failing_refresh)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    transport = httpx.MockTransport(handler)
    client = await canvas_client.get_client_for_user(
        db_session, logged_in_user.id, transport=transport
    )
    with pytest.raises(canvas_client.CanvasReauthRequired):
        await client.get_user_self()

    await db_session.refresh(cred)
    assert cred.status == "invalid"


def test_parse_next_link():
    header = (
        '<https://canvas.ust.hk/api/v1/users/self/courses?page=2&per_page=50>; rel="next", '
        '<https://canvas.ust.hk/api/v1/users/self/courses?page=5&per_page=50>; rel="last"'
    )
    assert (
        canvas_client._parse_next_link(header)
        == "https://canvas.ust.hk/api/v1/users/self/courses?page=2&per_page=50"
    )
    assert canvas_client._parse_next_link("") is None
    assert canvas_client._parse_next_link('<x>; rel="prev"') is None
