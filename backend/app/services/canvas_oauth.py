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

# Name of the HttpOnly cookie that binds an OAuth state JWT to the browser
# session that initiated it. Verified in the callback to block state-fixation
# attacks where a leaked state JWT is consumed by a different browser.
STATE_COOKIE_NAME = "canvas_oauth_nonce"


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


def encode_state(user_id: uuid.UUID) -> tuple[str, str]:
    """Return (state_jwt, nonce). The caller must set ``nonce`` as an
    HttpOnly cookie on the response so the callback can verify the request
    came from the same browser session that started the OAuth flow. The
    nonce is also embedded in the signed JWT; cookie match == session bind.
    """
    nonce = secrets.token_urlsafe(16)
    payload = {
        "uid": str(user_id),
        "nonce": nonce,
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }
    return (
        jwt.encode(payload, settings.canvas_state_secret, algorithm="HS256"),
        nonce,
    )


async def decode_state(token: str, cookie_nonce: str | None = None) -> uuid.UUID:
    """Verify signature, expiry, one-shot nonce, and — if supplied — the
    session-binding cookie nonce. ``cookie_nonce`` must match the JWT's
    ``nonce`` claim; a missing or mismatched cookie is rejected.
    """
    try:
        payload = jwt.decode(
            token,
            settings.canvas_state_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as exc:
        # Do not surface PyJWT's raw message — it can include token fragments
        # or other internals. `from exc` preserves the chain for tooling while
        # keeping the user-visible message generic.
        raise StateInvalid("JWT verification failed") from exc
    nonce = payload.get("nonce")
    exp = int(payload.get("exp", 0))
    if not nonce or not exp:
        raise StateInvalid("state token missing nonce/exp")
    if cookie_nonce is None or not secrets.compare_digest(cookie_nonce, nonce):
        raise StateInvalid("state cookie missing or does not match")
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
