"""Integration tests for the Canvas OAuth start/callback/disconnect endpoints."""

import pytest
from sqlalchemy import select

from app.models import CanvasUserCredential
from app.services import canvas_oauth
from app.services.crypto import decrypt_secret


@pytest.mark.asyncio
async def test_oauth_start_returns_authorize_url(
    async_client, logged_in_user, monkeypatch
):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_client_id", "cid")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "s")
    resp = await async_client.get("/api/canvas/oauth/start")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["authorize_url"].startswith(
        canvas_oauth.settings.canvas_base_url.rstrip("/")
    )
    assert "state=" in data["authorize_url"]


@pytest.mark.asyncio
async def test_oauth_callback_stores_credential(
    async_client, logged_in_user, db_session, monkeypatch
):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "s")
    state, nonce = canvas_oauth.encode_state(logged_in_user.id)

    async def fake_exchange(code):
        return {
            "access_token": "atk",
            "refresh_token": "rtk",
            "expires_in": 3600,
            "user": {"id": 42},
        }

    monkeypatch.setattr(canvas_oauth, "exchange_code", fake_exchange)

    resp = await async_client.get(
        f"/api/canvas/oauth/callback?code=xyz&state={state}",
        follow_redirects=False,
        cookies={canvas_oauth.STATE_COOKIE_NAME: nonce},
    )
    assert resp.status_code in (302, 303)

    row = (
        await db_session.execute(
            select(CanvasUserCredential).where(
                CanvasUserCredential.user_id == logged_in_user.id
            )
        )
    ).scalar_one()
    assert row.canvas_user_id == "42"
    assert decrypt_secret(row.access_token_encrypted) == "atk"
    assert decrypt_secret(row.refresh_token_encrypted) == "rtk"
    assert row.status == "active"


@pytest.mark.asyncio
async def test_oauth_callback_rejects_bad_state(async_client, monkeypatch):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "s")
    resp = await async_client.get(
        "/api/canvas/oauth/callback?code=xyz&state=not-a-real-jwt",
        follow_redirects=False,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_rejects_missing_cookie(
    async_client, logged_in_user, monkeypatch
):
    """Valid state JWT without the binding cookie must 400 ("Invalid or expired state")."""
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "s")
    state, _nonce = canvas_oauth.encode_state(logged_in_user.id)

    resp = await async_client.get(
        f"/api/canvas/oauth/callback?code=xyz&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_rejects_mismatched_cookie(
    async_client, logged_in_user, monkeypatch
):
    """Valid state JWT with the wrong cookie nonce must 400."""
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "s")
    state, _nonce = canvas_oauth.encode_state(logged_in_user.id)

    resp = await async_client.get(
        f"/api/canvas/oauth/callback?code=xyz&state={state}",
        follow_redirects=False,
        cookies={canvas_oauth.STATE_COOKIE_NAME: "not-the-right-nonce"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_disconnect_clears_credential(
    async_client, logged_in_user, db_session, monkeypatch
):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "s")
    state, nonce = canvas_oauth.encode_state(logged_in_user.id)

    async def fake_exchange(code):
        return {
            "access_token": "atk",
            "refresh_token": "rtk",
            "expires_in": 3600,
            "user": {"id": 7},
        }

    monkeypatch.setattr(canvas_oauth, "exchange_code", fake_exchange)
    await async_client.get(
        f"/api/canvas/oauth/callback?code=c&state={state}",
        follow_redirects=False,
        cookies={canvas_oauth.STATE_COOKIE_NAME: nonce},
    )

    resp = await async_client.delete("/api/canvas/connection")
    assert resp.status_code == 200

    row = (
        await db_session.execute(
            select(CanvasUserCredential).where(
                CanvasUserCredential.user_id == logged_in_user.id
            )
        )
    ).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_get_connection_status(
    async_client, logged_in_user, db_session, monkeypatch
):
    # Initially disconnected
    resp = await async_client.get("/api/canvas/connection")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"connected": False}

    # After OAuth dance, connected=True
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "s")
    state, nonce = canvas_oauth.encode_state(logged_in_user.id)

    async def fake_exchange(code):
        return {
            "access_token": "atk",
            "refresh_token": "rtk",
            "expires_in": 3600,
            "user": {"id": 7},
        }

    monkeypatch.setattr(canvas_oauth, "exchange_code", fake_exchange)
    await async_client.get(
        f"/api/canvas/oauth/callback?code=c&state={state}",
        follow_redirects=False,
        cookies={canvas_oauth.STATE_COOKIE_NAME: nonce},
    )

    resp = await async_client.get("/api/canvas/connection")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["connected"] is True
    assert data["canvas_user_id"] == "7"
