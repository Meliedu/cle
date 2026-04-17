"""Unit tests for canvas_oauth state helpers and URL builder."""

import time
import uuid

import pytest

from app.services import canvas_oauth


@pytest.mark.asyncio
async def test_state_round_trip(monkeypatch, db_session):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    user_id = uuid.uuid4()
    token, nonce = canvas_oauth.encode_state(user_id)
    decoded = await canvas_oauth.decode_state(token, nonce, db=db_session)
    assert decoded == user_id


@pytest.mark.asyncio
async def test_state_expired(monkeypatch):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    monkeypatch.setattr(canvas_oauth, "STATE_TTL_SECONDS", 1)
    token, nonce = canvas_oauth.encode_state(uuid.uuid4())
    time.sleep(2)
    with pytest.raises(canvas_oauth.StateInvalid):
        await canvas_oauth.decode_state(token, nonce)


@pytest.mark.asyncio
async def test_state_tampered(monkeypatch):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    token, nonce = canvas_oauth.encode_state(uuid.uuid4())
    with pytest.raises(canvas_oauth.StateInvalid):
        await canvas_oauth.decode_state(token + "x", nonce)


@pytest.mark.asyncio
async def test_state_replay_rejected(monkeypatch, db_session):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    token, nonce = canvas_oauth.encode_state(uuid.uuid4())
    # First use consumes the nonce.
    await canvas_oauth.decode_state(token, nonce, db=db_session)
    # Second use must be rejected as a replay.
    with pytest.raises(canvas_oauth.StateInvalid):
        await canvas_oauth.decode_state(token, nonce, db=db_session)


@pytest.mark.asyncio
async def test_state_missing_cookie_rejected(monkeypatch):
    """A valid state JWT without the binding cookie must be rejected."""
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    token, _nonce = canvas_oauth.encode_state(uuid.uuid4())
    with pytest.raises(canvas_oauth.StateInvalid):
        await canvas_oauth.decode_state(token, None)
    with pytest.raises(canvas_oauth.StateInvalid):
        await canvas_oauth.decode_state(token, "")


@pytest.mark.asyncio
async def test_state_mismatched_cookie_rejected(monkeypatch):
    """A valid state JWT paired with the wrong cookie nonce must be rejected."""
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    token, _nonce = canvas_oauth.encode_state(uuid.uuid4())
    with pytest.raises(canvas_oauth.StateInvalid):
        await canvas_oauth.decode_state(token, "definitely-not-the-nonce")


@pytest.mark.asyncio
async def test_state_correct_cookie_accepted(monkeypatch, db_session):
    """A valid state JWT paired with the matching cookie nonce succeeds."""
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    user_id = uuid.uuid4()
    token, nonce = canvas_oauth.encode_state(user_id)
    assert await canvas_oauth.decode_state(token, nonce, db=db_session) == user_id


def test_authorize_url(monkeypatch):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_client_id", "client123")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_base_url", "https://canvas.ust.hk")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_redirect_uri", "https://api.meli/cb")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_scopes", "url:GET|/api/v1/users/self")
    url = canvas_oauth.build_authorize_url(state="abc")
    assert url.startswith("https://canvas.ust.hk/login/oauth2/auth?")
    assert "client_id=client123" in url
    assert "state=abc" in url
    assert "scope=url%3AGET%7C%2Fapi%2Fv1%2Fusers%2Fself" in url
