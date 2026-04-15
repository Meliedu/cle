"""Canvas OAuth 2.0 state helpers and token exchange."""

from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings

STATE_TTL_SECONDS = 600  # 10 minutes


class StateInvalid(Exception):
    """Raised when the OAuth state token fails verification."""


# In-memory record of already-consumed state nonces. Bounded by STATE_TTL —
# expired entries are reaped on each check. In-memory is acceptable here
# because the callback is served by the same process that issued the state;
# re-auth in a rolling deploy window costs only one extra user flow, which
# is preferable to a replay in the single-process case.
_consumed_nonces: dict[str, int] = {}
_consumed_nonces_lock = asyncio.Lock()


async def _reap_expired_nonces(now: int) -> None:
    expired = [n for n, exp in _consumed_nonces.items() if exp <= now]
    for n in expired:
        _consumed_nonces.pop(n, None)


async def _consume_nonce(nonce: str, exp: int) -> None:
    """Record a nonce as used; raise StateInvalid if it was already consumed."""
    now = int(time.time())
    async with _consumed_nonces_lock:
        await _reap_expired_nonces(now)
        if nonce in _consumed_nonces:
            raise StateInvalid("state token already consumed")
        _consumed_nonces[nonce] = exp


def encode_state(user_id: uuid.UUID) -> str:
    payload = {
        "uid": str(user_id),
        "nonce": secrets.token_urlsafe(16),
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }
    return jwt.encode(payload, settings.canvas_state_secret, algorithm="HS256")


async def decode_state(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token,
            settings.canvas_state_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as exc:
        raise StateInvalid(str(exc)) from exc
    nonce = payload.get("nonce")
    exp = int(payload.get("exp", 0))
    if not nonce or not exp:
        raise StateInvalid("state token missing nonce/exp")
    await _consume_nonce(nonce, exp)
    return uuid.UUID(payload["uid"])


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.canvas_client_id,
        "response_type": "code",
        "redirect_uri": settings.canvas_redirect_uri,
        "state": state,
        "scope": settings.canvas_scopes,
    }
    return (
        f"{settings.canvas_base_url.rstrip('/')}/login/oauth2/auth?"
        + urlencode(params)
    )


async def exchange_code(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.canvas_base_url.rstrip('/')}/login/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.canvas_client_id,
                "client_secret": settings.canvas_client_secret,
                "redirect_uri": settings.canvas_redirect_uri,
                "code": code,
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Exchange a refresh token for a fresh access token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.canvas_base_url.rstrip('/')}/login/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.canvas_client_id,
                "client_secret": settings.canvas_client_secret,
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        return response.json()
