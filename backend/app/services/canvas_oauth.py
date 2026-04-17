"""Canvas OAuth 2.0 state helpers and token exchange."""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import jwt
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.oauth_nonce import OAuthConsumedNonce

STATE_TTL_SECONDS = 600  # 10 minutes

# Name of the HttpOnly cookie that binds an OAuth state JWT to the browser
# session that initiated it. Verified in the callback to block state-fixation
# attacks where a leaked state JWT is consumed by a different browser.
STATE_COOKIE_NAME = "canvas_oauth_nonce"


class StateInvalid(Exception):
    """Raised when the OAuth state token fails verification."""


async def _consume_nonce(db: AsyncSession, nonce: str, exp_ts: int) -> bool:
    """Atomically record a nonce as consumed.

    Returns True when the nonce is newly inserted, False when it was already
    present (i.e. a replay). Uses ``INSERT ... ON CONFLICT DO NOTHING`` so
    the check is atomic across workers — a second worker racing on the same
    nonce will see ``rowcount == 0`` and reject.

    The previous in-memory dict could not protect against replays when the
    callback was served by a different worker than the one that issued the
    state JWT.
    """
    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
    stmt = (
        pg_insert(OAuthConsumedNonce.__table__)
        .values(nonce=nonce, expires_at=expires_at)
        .on_conflict_do_nothing(index_elements=["nonce"])
    )
    result = await db.execute(stmt)
    await db.commit()
    return bool(result.rowcount)


async def prune_expired_nonces(db: AsyncSession) -> int:
    """Delete nonce rows whose ``expires_at`` is in the past.

    Safe to run periodically from a background scheduler; consumed nonces are
    only useful until their JWT would have expired anyway, after which any
    replay attempt is already rejected by the ``exp`` claim check.
    """
    result = await db.execute(
        sa.delete(OAuthConsumedNonce).where(
            OAuthConsumedNonce.expires_at < datetime.now(timezone.utc)
        )
    )
    await db.commit()
    return result.rowcount or 0


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


async def decode_state(
    token: str,
    cookie_nonce: str | None = None,
    db: AsyncSession | None = None,
) -> uuid.UUID:
    """Verify signature, expiry, one-shot nonce, and — if supplied — the
    session-binding cookie nonce. ``cookie_nonce`` must match the JWT's
    ``nonce`` claim; a missing or mismatched cookie is rejected.

    ``db`` must be provided so the consumed nonce can be recorded in the
    multi-worker-safe Postgres store. The request-path caller
    (``oauth_callback``) already holds an ``AsyncSession`` via ``get_db``.
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
    # Reject empty strings explicitly; compare_digest would return False anyway
    # but this makes intent clear.
    # NOTE: StateInvalid messages below are intentionally internal-only — the
    # API handler must catch StateInvalid generically and return a single
    # opaque 400 ("Invalid or expired state") so the distinct reasons aren't
    # surfaced to callers (would hand an attacker a cookie-presence oracle).
    if not cookie_nonce:
        raise StateInvalid("state cookie missing or empty")
    # NOTE: This StateInvalid message is intentionally internal-only; never
    # surface the distinct reason to the HTTP response (see note above).
    if not secrets.compare_digest(cookie_nonce, nonce):
        raise StateInvalid("state cookie does not match")
    if db is None:
        # Defensive: prior in-memory implementation did not require a db
        # parameter. Every in-tree caller now passes one; refuse to skip the
        # replay check silently.
        raise StateInvalid("state consumption requires database session")
    consumed = await _consume_nonce(db, nonce, exp)
    if not consumed:
        raise StateInvalid("state token already consumed")
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
