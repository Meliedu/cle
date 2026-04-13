"""Per-user rate limiting middleware using the api_usage table.

Counts requests per user per hour on the ``/api/rag/*`` endpoints. Limits are
configured via ``settings.student_rate_limit`` and
``settings.instructor_rate_limit``.

Flow: decode the Clerk JWT to identify the user, count recent rows in
``api_usage``, reject with 429 if over limit, otherwise call the wrapped app
and record a new row on the way back out so future requests are counted.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.database import async_session_factory
from app.models.api_usage import ApiUsage
from app.models.user import User
from app.services.auth import verify_clerk_token

logger = logging.getLogger(__name__)

_PUBLIC_PATH_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")


def _is_public_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES)


def _rate_limit_response(retry_after_seconds: int) -> dict:
    return {
        "success": False,
        "error": {
            "code": "RATE_LIMITED",
            "message": "Rate limit exceeded. Please try again later.",
            "retry_after": retry_after_seconds,
        },
    }


def _service_unavailable_response() -> dict:
    return {
        "success": False,
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "Rate limit service is temporarily unavailable.",
        },
    }


def _get_rate_limit(role: str) -> int:
    if role == "instructor":
        return settings.instructor_rate_limit
    return settings.student_rate_limit


async def _record_usage(user_id, endpoint: str) -> None:
    """Write an ApiUsage row. Best-effort: never propagates exceptions."""
    try:
        async with async_session_factory() as session:
            session.add(ApiUsage(user_id=user_id, endpoint=endpoint[:100]))
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to record api_usage for user=%s", user_id)


class RateLimitMiddleware:
    """Enforce per-user hourly request limits on /api/rag/* endpoints."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http",):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "").upper()

        # Skip OPTIONS, public paths, and non-API routes
        if method == "OPTIONS" or _is_public_path(path) or not path.startswith("/api"):
            await self.app(scope, receive, send)
            return

        # Only rate-limit AI generation endpoints, not every API call
        if not path.startswith("/api/rag/"):
            await self.app(scope, receive, send)
            return

        # GET reads under /api/rag/* (e.g. fetching a persisted course summary)
        # are not LLM calls and shouldn't count against the generation quota.
        if method == "GET":
            await self.app(scope, receive, send)
            return

        # Extract token from Authorization header
        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode("latin-1")

        if not auth_value.startswith("Bearer ") or len(auth_value) <= 7:
            # No valid auth header — let the auth middleware or deps handle it
            await self.app(scope, receive, send)
            return

        token = auth_value[7:]

        try:
            claims = verify_clerk_token(token)
        except Exception:
            # Invalid token — let the dependency layer return 401
            await self.app(scope, receive, send)
            return

        clerk_id = claims.get("sub")
        if not clerk_id:
            await self.app(scope, receive, send)
            return

        # Look up user and check rate limit
        user_id = None
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(User).where(User.clerk_id == clerk_id)
                )
                user = result.scalar_one_or_none()

                if user is None:
                    # New user — allow the request; deps will create them
                    await self.app(scope, receive, send)
                    return

                limit = _get_rate_limit(user.role)
                one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

                count_result = await session.execute(
                    select(func.count(ApiUsage.id)).where(
                        ApiUsage.user_id == user.id,
                        ApiUsage.created_at >= one_hour_ago,
                    )
                )
                request_count = count_result.scalar_one()

                if request_count >= limit:
                    # Log only opaque identifiers, not PII.
                    logger.warning(
                        "Rate limit exceeded for user_id=%s role=%s: %d/%d",
                        user.id,
                        user.role,
                        request_count,
                        limit,
                    )
                    body = json.dumps(_rate_limit_response(3600)).encode("utf-8")
                    response = Response(
                        content=body,
                        status_code=429,
                        media_type="application/json",
                        headers={"Retry-After": "3600"},
                    )
                    await response(scope, receive, send)
                    return

                user_id = user.id

        except Exception:
            # Fail closed: if we can't verify rate limits, deny rather than
            # silently allow unlimited requests through.
            logger.exception("Rate limit check failed — denying request")
            body = json.dumps(_service_unavailable_response()).encode("utf-8")
            response = Response(
                content=body,
                status_code=503,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return

        # Wrap send so we can observe the final status code and only count
        # successful requests against the quota (4xx/5xx should not burn it).
        status_code: dict[str, int] = {"code": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code["code"] = int(message.get("status", 0))
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if user_id is not None and 200 <= status_code["code"] < 300:
            await _record_usage(user_id, path)
