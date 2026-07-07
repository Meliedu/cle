"""Per-user rate limiting middleware using the api_usage table.

Enforces three disjoint per-user counting classes (see ``_classify_traffic``):

* Non-GET (LLM generation) — per-hour cap from ``settings.student_rate_limit``
  / ``settings.instructor_rate_limit``.
* GET (summary reads, job polling) — per-minute cap of 60 to prevent
  unbounded DB load from aggressive client polling.
* QR attendance scan (``/api/attend/{token}``, P3 T10) — its own per-minute
  cap so a scan flood cannot drain the generation quota (and vice-versa).

The read-check-insert sequence is serialised per user via a Postgres
advisory transaction lock (``pg_advisory_xact_lock``) so concurrent bursts
can't all observe count=0 before any INSERT lands and bypass the limit.
The usage row is *pre-inserted* inside the lock; if the downstream request
returns non-2xx we roll it back so failed calls don't burn the quota.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import func, select, text
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.database import async_session_factory
from app.models.api_usage import ApiUsage
from app.models.user import User
from app.services.auth import verify_jwt

logger = logging.getLogger(__name__)

_PUBLIC_PATH_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")

# Paths outside /api/rag/ that still invoke the LLM pipeline and therefore
# must share the same per-user rate limits.
_EXTRA_GENERATION_PATHS = ("/api/speech/generate-prompts",)

# Regexes to match LLM-backed endpoints whose path contains a course_id
# (so prefix-match is insufficient). Each POST to one of these kicks off
# an OpenRouter-billing job.
#
# - syllabus/imports: parses a syllabus PDF via the LLM (Phase 1).
# - concepts/extract:  samples chunks per document and asks the LLM for
#   candidate concepts (Phase 2 adaptive engine).
# - concepts/replay:   re-applies attempt evidence across a 90-day window;
#   while it isn't a per-row LLM call, it is an expensive instructor-only
#   batch job that must share the same per-user cap to prevent a single
#   instructor from queueing concurrent replays across many courses.
_RATE_LIMITED_REGEXES = (
    re.compile(r"^/api/courses/[^/]+/syllabus/imports$"),
    re.compile(r"^/api/courses/[^/]+/concepts/(?:extract|replay)$"),
)

# The QR attendance scan (P3 T10). Anchored on a single token segment so a
# nested/trailing-slash path never matches. It is rate-limited on its OWN
# per-minute counting class (below) so a scan flood cannot drain the RAG
# generation quota — and an exhausted RAG quota cannot block scans.
_ATTEND_SCAN_REGEX = re.compile(r"^/api/attend/[^/]+$")

# ``api_usage.endpoint`` prefix for a scan row. The disjoint count filter keys
# off this so the scan bucket and the generation bucket never count each other.
_ATTEND_ENDPOINT_PREFIX = "/api/attend/"

# Dedicated per-minute scan cap. A legitimate student scans once (with a couple
# of retries at most); a flood past this trips 429 on the scan bucket alone.
_ATTEND_SCAN_PER_MINUTE = 30


def _is_public_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES)


def _is_rate_limited_path(path: str) -> bool:
    if path.startswith("/api/rag/"):
        return True
    if path in _EXTRA_GENERATION_PATHS:
        return True
    if _ATTEND_SCAN_REGEX.match(path):
        return True
    return any(pattern.match(path) for pattern in _RATE_LIMITED_REGEXES)


def _classify_traffic(path: str, method: str) -> str:
    """The per-user counting class a rate-limited request belongs to.

    Three disjoint classes, each with its own cap and its own counted rows:

    * ``attend_scan`` — the QR scan (path-first, any method), per-minute cap.
    * ``get_poll``    — cheap GET reads/polls under a rate-limited prefix.
    * ``generation``  — everything else (LLM-billing POSTs), per-hour cap.
    """
    if _ATTEND_SCAN_REGEX.match(path):
        return "attend_scan"
    if method == "GET":
        return "get_poll"
    return "generation"


def _usage_count_filter(traffic_class: str):
    """The ``api_usage`` predicate isolating one class's rows from the others.

    The three filters are mutually exclusive and exhaustive, so a burst in one
    class can never be counted against another class's cap.
    """
    is_attend = ApiUsage.endpoint.like(_ATTEND_ENDPOINT_PREFIX + "%")
    if traffic_class == "attend_scan":
        return is_attend
    if traffic_class == "get_poll":
        return sa.and_(ApiUsage.method == "GET", sa.not_(is_attend))
    return sa.and_(ApiUsage.method != "GET", sa.not_(is_attend))


def _window_and_limit(traffic_class: str, role: str) -> tuple[timedelta, int, int]:
    """``(window, effective_limit, retry_after_seconds)`` for a counting class."""
    if traffic_class == "attend_scan":
        return timedelta(minutes=1), _ATTEND_SCAN_PER_MINUTE, 60
    if traffic_class == "get_poll":
        return timedelta(minutes=1), 60, 60
    return timedelta(hours=1), _get_rate_limit(role), 3600


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
        if not _is_rate_limited_path(path):
            await self.app(scope, receive, send)
            return

        # Each rate-limited request is bucketed into one of three disjoint
        # counting classes (see ``_classify_traffic``): the QR scan gets its own
        # per-minute cap, GET reads/polls a lighter per-minute cap, and LLM
        # generation the per-hour cap. Each class only ever counts its own rows.
        traffic_class = _classify_traffic(path, method)

        # Extract token from Authorization header
        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode("latin-1")

        if not auth_value.startswith("Bearer ") or len(auth_value) <= 7:
            # No valid auth header — let the auth middleware or deps handle it
            await self.app(scope, receive, send)
            return

        token = auth_value[7:]

        try:
            verified = verify_jwt(token)
        except Exception:
            # Invalid token — let the dependency layer return 401
            await self.app(scope, receive, send)
            return

        auth_user_id = verified.claims.get("sub")
        if not auth_user_id:
            await self.app(scope, receive, send)
            return

        # Look up user and check rate limit
        user_id = None
        reserved_usage_id = None
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(User).where(User.better_auth_id == auth_user_id)
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

                window, effective_limit, retry_after = _window_and_limit(
                    traffic_class, user.role
                )
                window_start = datetime.now(timezone.utc) - window

                # Each traffic class has its own cap and is counted against only
                # its own rows (see ``_usage_count_filter``). Mixing them caused
                # aggressive poll traffic to eat the hourly generation quota and
                # produce spurious 429s; the scan class keeps a QR-scan flood
                # from draining the generation quota (and vice-versa).
                count_result = await session.execute(
                    select(func.count(ApiUsage.id)).where(
                        ApiUsage.user_id == user.id,
                        ApiUsage.created_at >= window_start,
                        _usage_count_filter(traffic_class),
                    )
                )
                request_count = count_result.scalar_one()

                if request_count >= effective_limit:
                    # Log only opaque identifiers, not PII.
                    logger.warning(
                        "Rate limit exceeded for user_id=%s role=%s class=%s: %d/%d",
                        user.id,
                        user.role,
                        traffic_class,
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
