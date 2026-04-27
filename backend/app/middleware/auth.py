"""Lightweight ASGI middleware for early auth header validation.

This middleware rejects requests to /api/* paths that lack a Bearer token
in the Authorization header. It does NOT perform full JWT verification —
that responsibility belongs to the FastAPI dependency layer (app.api.deps).
"""

import json
import logging
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_PUBLIC_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    # OAuth redirect from Canvas — browser GET, no Bearer token possible.
    "/api/canvas/oauth/callback",
    # Service-to-service endpoints called by the Next.js Better Auth signup
    # hook. They authenticate via the X-Internal-Auth shared-secret header
    # checked inside the route, not via Bearer JWT.
    "/api/internal/",
)


def _is_public_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES)


def _unauthorized_response() -> dict:
    return {
        "success": False,
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Missing or invalid authorization header",
        },
    }


class AuthMiddleware:
    """Reject /api/* requests that have no Bearer token early, before routing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "").upper()

        # WebSocket auth is handled inside the endpoint (browser WS API
        # cannot send custom headers), so skip middleware check.
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        # Always allow CORS preflight, public paths, and non-API routes
        if method == "OPTIONS" or _is_public_path(path) or not path.startswith("/api"):
            await self.app(scope, receive, send)
            return

        # Check for Authorization: Bearer <token>
        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode("latin-1")
        if not auth_value.startswith("Bearer ") or len(auth_value) <= 7:
            logger.info("Auth rejected: no Bearer token for %s (header=%r)", path, auth_value[:20] if auth_value else "empty")
            body = json.dumps(_unauthorized_response()).encode("utf-8")
            response = Response(
                content=body,
                status_code=401,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
