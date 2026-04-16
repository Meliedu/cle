"""Inject baseline OWASP security headers on every response."""
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

_STATIC_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (
        b"permissions-policy",
        b"camera=(), microphone=(), geolocation=(), interest-cohort=()",
    ),
]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._hsts = (
            (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
            if settings.environment == "production"
            else None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                for name, value in _STATIC_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
                if self._hsts and b"strict-transport-security" not in existing:
                    headers.append(self._hsts)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
