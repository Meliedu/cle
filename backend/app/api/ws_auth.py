"""WebSocket bearer-token intake.

Browsers cannot set an ``Authorization`` header on a WebSocket, and putting the
JWT in the ``?token=`` query string leaks it into proxy and application access
logs (CWE-598: information exposure through a query string). So the token is
carried in the first WebSocket frame instead:

    {"type": "auth", "token": "<jwt>"}

The socket is accepted, the first frame is read and verified, and the connection
is closed with a policy-violation code if the frame is missing, malformed, or the
token does not verify. No token is ever read from the URL.
"""

import asyncio
import logging

from fastapi import WebSocket, status

from app.services.auth import VerifiedToken, verify_jwt

logger = logging.getLogger(__name__)

# Accept-then-auth means an unauthenticated peer holds a real connection until
# this fires, and there is no cap on concurrent unauthenticated sockets. Real
# clients send the frame from onopen, so this only needs to cover a slow
# network, not a slow user.
_AUTH_FRAME_TIMEOUT_S = 5.0


async def reject_ws(websocket: WebSocket) -> None:
    """Close an already-accepted WebSocket with a policy-violation (1008) code.

    Used by endpoints for their own post-auth rejections (unknown user, ownership
    or enrollment failure) so the close bookkeeping stays in one place.

    Closing is best-effort. The most common reason we get here is that the client
    disconnected mid-handshake, and closing a socket the peer already abandoned
    raises. Letting that escape would turn a routine disconnect into an unhandled
    exception in an endpoint that has no handler for it.
    """
    try:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    except Exception:  # noqa: BLE001, the peer is already gone; nothing to do
        logger.debug("WS close failed (peer likely already disconnected)", exc_info=True)


async def authenticate_ws(websocket: WebSocket) -> VerifiedToken | None:
    """Accept the socket, read + verify the first-frame auth token.

    Returns the verified token on success. On any failure (missing/slow/malformed
    first frame, or an invalid token) it closes the socket and returns ``None``;
    the caller must simply ``return``. Downstream authorization (user resolution,
    ownership, enrollment) stays in each endpoint, which calls ``reject_ws`` for
    its own rejections.
    """
    await websocket.accept()
    try:
        frame = await asyncio.wait_for(
            websocket.receive_json(), timeout=_AUTH_FRAME_TIMEOUT_S
        )
    except Exception:  # noqa: BLE001, timeout / disconnect / non-JSON all reject
        await reject_ws(websocket)
        return None

    token: str | None = None
    if isinstance(frame, dict) and frame.get("type") == "auth":
        candidate = frame.get("token")
        if isinstance(candidate, str) and candidate:
            token = candidate
    if not token:
        await reject_ws(websocket)
        return None

    try:
        verified = verify_jwt(token)
    except Exception as exc:  # noqa: BLE001, any verify failure is a policy reject
        logger.warning("WS auth failed: %s", exc.__class__.__name__)
        await reject_ws(websocket)
        return None
    if not verified.claims.get("sub"):
        await reject_ws(websocket)
        return None
    return verified
