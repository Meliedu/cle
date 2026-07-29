"""Regression: one test detaching the event loop must not fail the suite.

pytest-asyncio installs its session-scoped loop exactly once. Anything that
calls ``asyncio.run`` (or ``asyncio.set_event_loop(None)``) leaves the policy
with ``_local._loop is None`` and ``_set_called`` already True, so every later
``asyncio.get_event_loop()`` raises ``RuntimeError: There is no current event
loop in thread 'MainThread'``. Historically that turned a single stray
``asyncio.run`` in ``test_seed_exclusion.py`` into 75 failures spread across
every async test module collected after it.

The ``_preserve_current_event_loop`` autouse fixture in ``conftest.py`` repairs
the loop between tests. These three tests run in source order and pin that
behaviour end to end.
"""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_a_session_loop_is_running():
    """Force the session-scoped loop into existence before the hazard below.

    Without this the poisoning test could run before any async test, and
    pytest-asyncio would install a fresh loop afterwards on its own, which
    would let the regression pass for the wrong reason.
    """
    assert asyncio.get_running_loop() is not None


def test_b_detaching_the_loop_is_survivable():
    """Simulate the hazard: a sync test that runs its own event loop."""

    async def noop():
        return "done"

    assert asyncio.run(noop()) == "done"


@pytest.mark.asyncio
async def test_c_async_tests_still_run_after_detachment():
    """The real assertion: this test existing and running at all.

    Before the fix it failed during setup with RuntimeError, never reaching
    its body.
    """
    await asyncio.sleep(0)
    assert asyncio.get_running_loop() is not None


def test_d_current_loop_is_reinstalled():
    """The policy must hand back a usable loop, not raise and not a closed one."""
    loop = asyncio.get_event_loop_policy().get_event_loop()
    assert not loop.is_closed()
