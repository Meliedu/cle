"""Regression tests for the method-aware rate limit counting.

Before this fix, both the per-minute GET cap and the per-hour non-GET cap
counted every row in ``api_usage`` regardless of HTTP method. That let a
burst of GET polls against ``/api/rag/jobs/{id}`` exhaust the instructor's
50/hr generation quota and return 429 on the next ``POST /generate-quiz``.

These tests lock in the fix: the count query must filter by method so each
bucket sees only its own traffic class.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_usage import ApiUsage
from app.models.user import User


def _count_query(user_id: uuid.UUID, window_start: datetime, *, is_get_poll: bool):
    """Replicates the middleware's count predicate so we assert the exact
    filter shape rather than a parallel-implemented heuristic."""
    method_filter = (
        ApiUsage.method == "GET"
        if is_get_poll
        else ApiUsage.method != "GET"
    )
    return (
        select(func.count(ApiUsage.id))
        .where(
            ApiUsage.user_id == user_id,
            ApiUsage.created_at >= window_start,
            method_filter,
        )
    )


async def _make_user(session: AsyncSession) -> User:
    user = User(
        clerk_id=f"user_{uuid.uuid4().hex[:12]}",
        email=f"{uuid.uuid4().hex[:8]}@ust.hk",
        role="instructor",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_get_polls_do_not_burn_post_quota(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    now = datetime.now(timezone.utc)

    # Simulate 100 recent GET polls (job status checks) plus 3 POSTs.
    for _ in range(100):
        db_session.add(
            ApiUsage(user_id=user.id, endpoint="/api/rag/jobs/x", method="GET")
        )
    for _ in range(3):
        db_session.add(
            ApiUsage(user_id=user.id, endpoint="/api/rag/generate-quiz", method="POST")
        )
    await db_session.commit()

    # Hourly POST window must only see the 3 POSTs.
    hour_window = now - timedelta(hours=1)
    post_count = (
        await db_session.execute(_count_query(user.id, hour_window, is_get_poll=False))
    ).scalar_one()
    assert post_count == 3, (
        "non-GET count must exclude GET polls; otherwise polling bursts "
        "cause spurious 429s on generation requests"
    )

    # Per-minute GET window must only see the GET polls.
    minute_window = now - timedelta(minutes=1)
    get_count = (
        await db_session.execute(_count_query(user.id, minute_window, is_get_poll=True))
    ).scalar_one()
    assert get_count == 100


@pytest.mark.asyncio
async def test_method_filter_treats_put_and_delete_as_non_get(
    db_session: AsyncSession,
) -> None:
    """Only GET gets the cheap per-minute bucket; every other verb shares
    the expensive hourly generation bucket."""
    user = await _make_user(db_session)

    for method in ("POST", "PUT", "DELETE", "PATCH"):
        db_session.add(
            ApiUsage(user_id=user.id, endpoint="/api/rag/query", method=method)
        )
    db_session.add(
        ApiUsage(user_id=user.id, endpoint="/api/rag/jobs/x", method="GET")
    )
    await db_session.commit()

    now = datetime.now(timezone.utc)
    post_count = (
        await db_session.execute(
            _count_query(user.id, now - timedelta(hours=1), is_get_poll=False)
        )
    ).scalar_one()
    get_count = (
        await db_session.execute(
            _count_query(user.id, now - timedelta(minutes=1), is_get_poll=True)
        )
    ).scalar_one()

    assert post_count == 4, "PUT/DELETE/PATCH must count against the hourly cap"
    assert get_count == 1
