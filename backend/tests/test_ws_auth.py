"""Unit tests for the first-frame WebSocket handshake (CWE-598 remediation).

The JWT used to travel in the ``?token=`` query string, where it lands in proxy
and application access logs. It now arrives in the first frame instead. The
security property is that ``authenticate_ws`` FAILS CLOSED on every malformed,
missing, slow, or invalid input.

Before these tests, that property was only exercised by
``frontend/scripts/live-monitor-check.mjs``, a manual harness needing a running
stack and hand-supplied UUIDs. That proves the wire format but cannot gate CI,
which is the wrong shape for a security fix: the reject branches are exactly
what an attacker probes.
"""

import asyncio

import pytest
from fastapi import WebSocketDisconnect

from app.api import ws_auth


class FakeWebSocket:
    """Minimal WebSocket double recording accept/close and serving queued frames."""

    def __init__(self, incoming: list | None = None, *, hang: bool = False) -> None:
        self._incoming = list(incoming or [])
        self._hang = hang
        self.accepted = False
        self.closed = False
        self.close_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def receive_json(self):
        if self._hang:
            # Outlive the auth-frame timeout without ever sending anything.
            await asyncio.sleep(3600)
        if not self._incoming:
            raise WebSocketDisconnect(code=1000)
        return self._incoming.pop(0)

    async def close(self, code: int = 1000) -> None:
        self.closed = True
        self.close_code = code


def _verified(claims: dict):
    class _V:
        def __init__(self) -> None:
            self.claims = claims

    return _V()


async def _assert_rejected(ws: FakeWebSocket) -> None:
    result = await ws_auth.authenticate_ws(ws)
    assert result is None, "authenticate_ws must return None on rejection"
    assert ws.accepted, "the socket is accepted before the frame can be read"
    assert ws.closed, "a rejected socket must be closed, not left open"
    assert ws.close_code == 1008, f"expected policy-violation 1008, got {ws.close_code}"


@pytest.mark.asyncio
async def test_no_frame_at_all_is_rejected():
    """A client that connects and immediately disconnects."""
    await _assert_rejected(FakeWebSocket([]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frame",
    [
        pytest.param({"type": "chat"}, id="wrong-type"),
        pytest.param({"type": "auth"}, id="no-token-key"),
        pytest.param({"type": "auth", "token": ""}, id="empty-token"),
        pytest.param({"type": "auth", "token": None}, id="null-token"),
        pytest.param({"type": "auth", "token": 12345}, id="non-string-token"),
        pytest.param({"token": "x"}, id="no-type-key"),
        pytest.param("hello", id="bare-string"),
        pytest.param([], id="bare-list"),
        pytest.param(None, id="bare-null"),
    ],
)
async def test_malformed_first_frame_is_rejected(frame):
    await _assert_rejected(FakeWebSocket([frame]))


@pytest.mark.asyncio
async def test_invalid_token_is_rejected(monkeypatch):
    def boom(_token: str):
        raise ValueError("bad signature")

    monkeypatch.setattr(ws_auth, "verify_jwt", boom)
    await _assert_rejected(FakeWebSocket([{"type": "auth", "token": "not-a-jwt"}]))


@pytest.mark.asyncio
async def test_token_without_sub_claim_is_rejected(monkeypatch):
    """A structurally valid token that identifies nobody must not authenticate."""
    monkeypatch.setattr(ws_auth, "verify_jwt", lambda _t: _verified({"aud": "meli"}))
    await _assert_rejected(FakeWebSocket([{"type": "auth", "token": "sub-less"}]))


@pytest.mark.asyncio
async def test_empty_sub_claim_is_rejected(monkeypatch):
    monkeypatch.setattr(ws_auth, "verify_jwt", lambda _t: _verified({"sub": ""}))
    await _assert_rejected(FakeWebSocket([{"type": "auth", "token": "blank-sub"}]))


@pytest.mark.asyncio
async def test_silent_client_is_rejected_on_timeout(monkeypatch):
    """A client that holds the socket open without authenticating.

    Accept-then-auth means an unauthenticated peer occupies a real connection
    until this timeout fires, so the timeout is what bounds that exposure.
    """
    monkeypatch.setattr(ws_auth, "_AUTH_FRAME_TIMEOUT_S", 0.05)
    ws = FakeWebSocket(hang=True)
    await asyncio.wait_for(_assert_rejected(ws), timeout=5)


@pytest.mark.asyncio
async def test_valid_token_is_accepted_and_socket_left_open(monkeypatch):
    monkeypatch.setattr(ws_auth, "verify_jwt", lambda _t: _verified({"sub": "user-1"}))
    ws = FakeWebSocket([{"type": "auth", "token": "good"}])

    verified = await ws_auth.authenticate_ws(ws)

    assert verified is not None
    assert verified.claims["sub"] == "user-1"
    assert ws.accepted
    assert not ws.closed, "a successful handshake must leave the socket open"


@pytest.mark.asyncio
async def test_reject_ws_survives_an_already_gone_peer():
    """Closing a socket the client abandoned must not raise into the endpoint."""

    class Gone(FakeWebSocket):
        async def close(self, code: int = 1000) -> None:
            raise RuntimeError("connection already closed")

    await ws_auth.reject_ws(Gone())  # must not raise


@pytest.mark.asyncio
async def test_token_is_never_read_from_the_url(monkeypatch):
    """The whole point of the fix: a token in the query string is ignored.

    A socket carrying ``?token=`` in its URL but sending no auth frame must be
    rejected exactly like any other silent client.
    """
    monkeypatch.setattr(ws_auth, "verify_jwt", lambda _t: _verified({"sub": "user-1"}))

    class WithQueryToken(FakeWebSocket):
        url = "ws://test/api/checkpoints/abc/monitor?token=a.valid.looking.jwt"
        query_params = {"token": "a.valid.looking.jwt"}

    await _assert_rejected(WithQueryToken([]))
