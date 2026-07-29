"""Regression: one test detaching the event loop must not fail the suite.

pytest-asyncio installs its session-scoped loop exactly once. Anything that
calls ``asyncio.run`` (or ``asyncio.set_event_loop(None)``) leaves the policy
with ``_local._loop is None`` and ``_set_called`` already True, so every later
``asyncio.get_event_loop()`` raises ``RuntimeError: There is no current event
loop in thread 'MainThread'``. Historically that turned a single stray
``asyncio.run`` in ``test_seed_exclusion.py`` into 75 failures spread across
every async test module collected after it.

The ``_preserve_current_event_loop`` autouse fixture in ``conftest.py`` repairs
the loop between tests. These tests run in source order and pin that behaviour
end to end; ``test_e`` makes that ordering assumption executable.
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

    Before the fix it failed in the CALL phase with RuntimeError, never
    reaching its body. (Not setup: async fixtures resolve their loop through
    cached ``getfixturevalue`` and never call ``get_event_loop``; the raise
    comes from pytest-asyncio's ``pytest_pyfunc_call`` wrapper.)
    """
    await asyncio.sleep(0)
    assert asyncio.get_running_loop() is not None


def test_d_current_loop_is_reinstalled():
    """The policy must hand back a usable loop, not raise and not a closed one."""
    loop = asyncio.get_event_loop_policy().get_event_loop()
    assert not loop.is_closed()


def test_e_ordering_assumption_is_real():
    """This module only tests anything if its tests share a process, in order.

    Under pytest-xdist the poisoning test and the test that proves recovery can
    land in different workers, and under pytest-randomly they can be reordered.
    Either way every test above would pass whether or not the guard exists, and
    this file would quietly stop being a regression test. Fail loudly instead of
    degrading into decoration.
    """
    import sys

    for plugin in ("xdist", "pytest_randomly", "pytest_random_order"):
        assert plugin not in sys.modules, (
            f"{plugin} is active; tests/test_event_loop_guard.py depends on "
            "same-process, source-order execution and is no longer meaningful. "
            "Pin this module to one worker (e.g. @pytest.mark.xdist_group) or "
            "rewrite it as a direct unit test of the conftest fixture."
        )
