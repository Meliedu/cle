"""Cross-worker refresh serialization via Postgres advisory lock.

Two parallel acquires on the same user_id must execute non-interleaved.
Uses separate ``AsyncSession`` instances so each holds a distinct Postgres
backend connection — this is what actually happens across multiple uvicorn
workers or a worker + web process sharing one database.
"""

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.canvas_client import _acquire_refresh_lock
from tests.conftest import test_session_factory as session_factory


@pytest.mark.asyncio
async def test_concurrent_refresh_serialized(db_session: AsyncSession):
    """Two parallel acquires on the same user_id serialise via pg advisory lock."""
    uid = uuid.uuid4()
    events: list[str] = []

    async def worker(tag: str) -> None:
        # Each worker uses its own AsyncSession (its own Postgres backend
        # connection). That's the only way the advisory lock demonstrates
        # serialization — pg_advisory_lock is session-level and reentrant on
        # the same session, so sharing a session would trivially "pass" this
        # test without proving anything.
        async with session_factory() as session:
            async with _acquire_refresh_lock(session, uid):
                events.append(f"{tag}-in")
                await asyncio.sleep(0.05)
                events.append(f"{tag}-out")

    await asyncio.gather(worker("a"), worker("b"))
    # Must NOT interleave: a-in, a-out, b-in, b-out (or reversed order)
    assert events in (
        ["a-in", "a-out", "b-in", "b-out"],
        ["b-in", "b-out", "a-in", "a-out"],
    )
