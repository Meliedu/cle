"""Regression tests for durable cron watermarks.

Earlier the worker tracked cron state in an in-memory dict that was seeded
fresh on every boot and advanced unconditionally — even when the body
raised. ``_claim_and_run_cron`` now persists ``last_success_at`` in
``cron_runs`` and only advances it after the body succeeds.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import CronRun
from app.services import worker as worker_module
from app.services.worker import _claim_and_run_cron
from tests.conftest import test_session_factory


@pytest_asyncio.fixture(autouse=True)
async def _redirect_cron_to_test_db(monkeypatch, db_session):
    """Point the cron helper's session factory at the test database so
    ``cron_runs`` writes are visible to the test's ``db_session``."""
    monkeypatch.setattr(
        worker_module, "async_session_factory", test_session_factory
    )
    yield


@pytest.mark.asyncio
async def test_cron_advances_only_on_success(db_session):
    calls: list[str] = []

    async def body() -> None:
        calls.append("ran")

    await _claim_and_run_cron("regression_ok", timedelta(seconds=0), body)

    await db_session.rollback()
    row = (
        await db_session.execute(
            select(CronRun).where(CronRun.name == "regression_ok")
        )
    ).scalar_one()
    assert calls == ["ran"]
    # Recorded a real watermark (i.e. moved off the lazy epoch seed).
    assert row.last_success_at > datetime(1970, 1, 2, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_cron_failure_does_not_advance_watermark(db_session):
    """Body raising must leave last_success_at unchanged so the next tick
    retries immediately instead of waiting a full cadence interval."""
    calls: list[str] = []

    async def body() -> None:
        calls.append("attempt")
        raise RuntimeError("simulated transient failure")

    await _claim_and_run_cron("regression_fail", timedelta(seconds=0), body)

    await db_session.rollback()
    row = (
        await db_session.execute(
            select(CronRun).where(CronRun.name == "regression_fail")
        )
    ).scalar_one()
    assert calls == ["attempt"]
    # Still at the lazy-seeded epoch — body raised before watermark advanced.
    assert row.last_success_at <= datetime(1970, 1, 2, tzinfo=timezone.utc)

    # A subsequent tick fires again (cadence isn't satisfied because the
    # watermark didn't move).
    async def body_ok() -> None:
        calls.append("retry")

    await _claim_and_run_cron("regression_fail", timedelta(seconds=0), body_ok)
    assert calls == ["attempt", "retry"]


@pytest.mark.asyncio
async def test_cron_skips_when_within_cadence(db_session):
    """A second call within the cadence window doesn't run the body."""
    calls: list[str] = []

    async def body() -> None:
        calls.append("ran")

    await _claim_and_run_cron("regression_cadence", timedelta(seconds=0), body)
    # Big cadence — the watermark just set above is well within it.
    await _claim_and_run_cron("regression_cadence", timedelta(hours=24), body)
    assert calls == ["ran"]


@pytest.mark.asyncio
async def test_cron_advisory_lock_prevents_concurrent_runs(db_session):
    """Two ``_claim_and_run_cron`` calls in flight at once for the same name
    serialize: the second sees the advisory lock held and returns
    immediately, leaving the body run exactly once."""
    import asyncio

    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def slow_body() -> None:
        calls.append("start")
        started.set()
        await release.wait()
        calls.append("end")

    async def fast_body() -> None:
        calls.append("contender")

    async def runner_a():
        await _claim_and_run_cron(
            "regression_concurrent", timedelta(seconds=0), slow_body
        )

    async def runner_b():
        await started.wait()
        await _claim_and_run_cron(
            "regression_concurrent", timedelta(seconds=0), fast_body
        )
        release.set()

    await asyncio.gather(runner_a(), runner_b())
    # ``contender`` saw the advisory lock held and returned early; only
    # the slow body ran.
    assert "contender" not in calls
    assert calls == ["start", "end"]
