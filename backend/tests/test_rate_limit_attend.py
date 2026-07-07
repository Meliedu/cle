"""P3 T10 — QR scan rate-limit extension.

``POST /api/attend/{token}`` gets its OWN per-minute cap on a dedicated
counting class so a scan flood can't drain the RAG generation quota (and a
drained RAG quota can't block scans). The scanning student is authenticated,
so the existing verify_jwt -> user lookup keys the limit per user.

Two layers of coverage:

* Pure-function tests pin the matcher, the traffic classifier and the disjoint
  count filters (the crux: the scan bucket and the generation bucket never
  count each other's rows).
* Driven-middleware tests exercise the real ``RateLimitMiddleware`` ASGI path
  against the test DB and assert the actual 429 behaviour in both directions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.middleware import rate_limit
from app.middleware.rate_limit import (
    _ATTEND_SCAN_PER_MINUTE,
    RateLimitMiddleware,
    _classify_traffic,
    _is_rate_limited_path,
    _usage_count_filter,
)
from app.models.api_usage import ApiUsage
from app.models.user import User


def _scan_path() -> str:
    return f"/api/attend/{uuid.uuid4().hex}"


# ----- matcher -----

def test_attend_scan_path_matches() -> None:
    assert _is_rate_limited_path(_scan_path()) is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/attend",       # missing token segment
        "/api/attend/",      # empty token
        "/api/attend/a/b",   # nested — a token can't contain a slash
        "/api/attend/tok/",  # trailing slash must NOT match ($-anchored)
    ],
)
def test_attend_scan_path_anchored(path: str) -> None:
    assert _is_rate_limited_path(path) is False


# ----- traffic classification -----

def test_classify_attend_scan_by_path() -> None:
    # Any method to the scan path is the attend_scan class (path-first).
    assert _classify_traffic("/api/attend/tok", "POST") == "attend_scan"
    assert _classify_traffic("/api/attend/tok", "GET") == "attend_scan"


def test_classify_generation_and_get_poll() -> None:
    assert _classify_traffic("/api/rag/query", "POST") == "generation"
    assert _classify_traffic("/api/rag/jobs/x", "GET") == "get_poll"


# ----- disjoint count filters (the crux) -----

async def _make_student(session: AsyncSession) -> User:
    user = User(
        better_auth_id=f"scan_{uuid.uuid4().hex[:12]}",
        email=f"{uuid.uuid4().hex[:8]}@connect.ust.hk",
        role="student",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_scan_and_generation_buckets_are_disjoint(
    db_session: AsyncSession,
) -> None:
    """40 scans, 5 RAG POSTs, 7 GET polls — each class filter must see ONLY its
    own traffic, so a scan flood never counts against RAG (and vice-versa)."""
    user = await _make_student(db_session)
    for _ in range(40):
        db_session.add(
            ApiUsage(
                user_id=user.id,
                endpoint=f"/api/attend/{uuid.uuid4().hex}",
                method="POST",
            )
        )
    for _ in range(5):
        db_session.add(
            ApiUsage(user_id=user.id, endpoint="/api/rag/generate-quiz", method="POST")
        )
    for _ in range(7):
        db_session.add(
            ApiUsage(user_id=user.id, endpoint="/api/rag/jobs/x", method="GET")
        )
    await db_session.commit()
    now = datetime.now(timezone.utc)

    async def _count(traffic_class: str, window: timedelta) -> int:
        return (
            await db_session.execute(
                select(func.count(ApiUsage.id)).where(
                    ApiUsage.user_id == user.id,
                    ApiUsage.created_at >= now - window,
                    _usage_count_filter(traffic_class),
                )
            )
        ).scalar_one()

    assert await _count("attend_scan", timedelta(minutes=1)) == 40
    assert await _count("generation", timedelta(hours=1)) == 5
    assert await _count("get_poll", timedelta(minutes=1)) == 7


# ----- driven middleware (real 429 behaviour) -----

async def _ok_app(scope, receive, send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


async def _drive(mw: RateLimitMiddleware, path: str, method: str) -> int:
    scope = {
        "type": "http",
        "path": path,
        "method": method,
        "headers": [(b"authorization", b"Bearer scan-token")],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    captured: dict[str, int] = {}

    async def send(message) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = int(message["status"])

    await mw(scope, receive, send)
    return captured["status"]


class _Verified:
    def __init__(self, sub: str) -> None:
        self.claims = {"sub": sub}


def _patch_middleware(monkeypatch, db_session: AsyncSession, user: User) -> None:
    factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(rate_limit, "async_session_factory", factory)
    monkeypatch.setattr(
        rate_limit, "verify_jwt", lambda _tok: _Verified(user.better_auth_id)
    )


@pytest.mark.asyncio
async def test_scan_flood_429s_without_burning_rag(
    db_session: AsyncSession, monkeypatch
) -> None:
    user = await _make_student(db_session)
    _patch_middleware(monkeypatch, db_session, user)
    mw = RateLimitMiddleware(_ok_app)

    # The per-minute scan cap is spent by the flood.
    for i in range(_ATTEND_SCAN_PER_MINUTE):
        assert await _drive(mw, _scan_path(), "POST") == 200, f"scan {i} should pass"
    # The next scan trips the dedicated per-minute cap.
    assert await _drive(mw, _scan_path(), "POST") == 429

    # ...but the RAG generation quota is untouched — a POST still passes.
    assert await _drive(mw, "/api/rag/query", "POST") == 200


@pytest.mark.asyncio
async def test_rag_exhaustion_does_not_block_scans(
    db_session: AsyncSession, monkeypatch
) -> None:
    user = await _make_student(db_session)
    # Exhaust the hourly generation quota directly (student cap is 10).
    for _ in range(50):
        db_session.add(
            ApiUsage(user_id=user.id, endpoint="/api/rag/query", method="POST")
        )
    await db_session.commit()

    _patch_middleware(monkeypatch, db_session, user)
    mw = RateLimitMiddleware(_ok_app)

    # RAG generation is now blocked...
    assert await _drive(mw, "/api/rag/query", "POST") == 429
    # ...but a QR scan still succeeds on its own bucket.
    assert await _drive(mw, _scan_path(), "POST") == 200
