"""Per-user rate limiting middleware using the api_usage table.

Enforces two limits on ``/api/rag/*``:

* Non-GET (LLM generation) — per-hour cap from ``settings.student_rate_limit``
  / ``settings.instructor_rate_limit``.
* GET (summary reads, job polling) — per-minute cap of 60 to prevent
  unbounded DB load from aggressive client polling.

The read-check-insert sequence is serialised per user via a Postgres
advisory transaction lock (``pg_advisory_xact_lock``) so concurrent bursts
can't all observe count=0 before any INSERT lands and bypass the limit.
The usage row is *pre-inserted* inside the lock; if the downstream request
returns non-2xx we roll it back so failed calls don't burn the quota.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import func, select, text
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

        # GET reads under /api/rag/* (e.g. fetching a persisted course summary
        # or polling a job) are cheap individually but can hammer the DB under
        # aggressive client polling. Apply a lighter per-minute cap instead of
        # bypassing the limiter entirely.
        is_get_poll = method == "GET"

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
        reserved_usage_id = None
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

                # Serialise the read-check-insert sequence per user via an
                # advisory transaction lock. Held only for the microseconds of
                # the COUNT+INSERT, NOT for the duration of the downstream LLM
                # call, so concurrent requests from different users are not
                # blocked and a single user's bursts can't bypass the limit by
                # all observing count=0 before any INSERT lands.
                lock_key = f"ratelimit:{user.id}"
                await session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock(hashtext(:k)::bigint)"
                    ).bindparams(k=lock_key)
                )

                window = timedelta(minutes=1) if is_get_poll else timedelta(hours=1)
                effective_limit = 60 if is_get_poll else _get_rate_limit(user.role)
                window_start = datetime.now(timezone.utc) - window

                # Each traffic class (GET polling vs non-GET generation) has
                # its own cap and must be counted against only its own rows.
                # Mixing them caused aggressive poll traffic to eat the
                # hourly generation quota and produce spurious 429s.
                method_filter = (
                    ApiUsage.method == "GET"
                    if is_get_poll
                    else ApiUsage.method != "GET"
                )
                count_result = await session.execute(
                    select(func.count(ApiUsage.id)).where(
                        ApiUsage.user_id == user.id,
                        ApiUsage.created_at >= window_start,
                        method_filter,
                    )
                )
                request_count = count_result.scalar_one()

                if request_count >= effective_limit:
                    retry_after = 60 if is_get_poll else 3600
                    # Log only opaque identifiers, not PII.
                    logger.warning(
                        "Rate limit exceeded for user_id=%s role=%s window=%s: %d/%d",
                        user.id,
                        user.role,
                        "1m" if is_get_poll else "1h",
                        request_count,
                        effective_limit,
                    )
                    body = json.dumps(_rate_limit_response(retry_after)).encode("utf-8")
                    response = Response(
                        content=body,
                        status_code=429,
                        media_type="application/json",
                        headers={"Retry-After": str(retry_after)},
                    )
                    await response(scope, receive, send)
                    return

                # Reserve the slot now — pre-insert the usage row inside the
                # advisory-lock-protected transaction. If the downstream
                # request fails (non-2xx) we delete this row below so failed
                # calls don't burn the quota.
                usage = ApiUsage(
                    user_id=user.id,
                    endpoint=path[:100],
                    method=method[:8],
                )
                session.add(usage)
                await session.commit()
                await session.refresh(usage)
                reserved_usage_id = usage.id
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

        # Wrap send so we can observe the final status code. The usage row is
        # already reserved; if the downstream request fails (non-2xx) we roll
        # it back so failed calls don't burn the user's quota.
        status_code: dict[str, int] = {"code": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code["code"] = int(message.get("status", 0))
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if (
            user_id is not None
            and reserved_usage_id is not None
            and not (200 <= status_code["code"] < 300)
        ):
            try:
                async with async_session_factory() as rollback_session:
                    await rollback_session.execute(
                        sa.delete(ApiUsage).where(ApiUsage.id == reserved_usage_id)
                    )
                    await rollback_session.commit()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to roll back reserved rate-limit row")
