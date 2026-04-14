"""Canvas OAuth 2.0 state helpers and token exchange."""

from __future__ import annotations

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


def encode_state(user_id: uuid.UUID) -> str:
    payload = {
        "uid": str(user_id),
        "nonce": secrets.token_urlsafe(16),
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }
    return jwt.encode(payload, settings.canvas_state_secret, algorithm="HS256")


def decode_state(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token,
            settings.canvas_state_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as exc:
        raise StateInvalid(str(exc)) from exc
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
