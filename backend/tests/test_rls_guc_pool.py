"""Pooled-connection RLS GUC regression test (P7 Task B10, Decision 7).

Tracked finding (P2 Task 8): ``deps.py::get_current_user`` sets the
``app.current_user_id`` GUC session-scoped (``set_config(..., false)``) so a
value can outlive the request on a POOLED physical connection. ``database.py``
already resets the GUC to ``''`` on every pool **checkout** (``_reset_rls_context``),
so a borrowed connection starts blank and ``current_setting(...,true)::uuid`` on
a blank GUC RAISES → fails closed (no leak). B10 adds a SYMMETRIC **checkin**
reset (``_reset_rls_on_checkin``) as defense-in-depth so a value never lingers in
an idle pooled connection between requests.

These tests prove the fail-closed + no-leak behaviour end-to-end and assert BOTH
ends of the pool cycle are wired:

  * A raw pooled connection acquired WITHOUT going through ``get_current_user``
    observes a blank GUC; an RLS-table SELECT under ``SET ROLE meli_app`` with the
    blank GUC FAILS CLOSED (``''::uuid`` raises) — never leaks a prior request's
    rows.
  * After a request sets the GUC and the connection returns to the pool, the NEXT
    checkout sees blank again (checkin + checkout reset).
  * The checkin listener resets the GUC IN ISOLATION (with the checkout listener
    temporarily detached) — proving the new listener does real work, not just
    riding on the pre-existing checkout reset.

Skip-guard: the RLS fail-closed assertion needs the non-superuser ``meli_app``
role (no ``BYPASSRLS``; ``postgres`` has it, per migration ``28236be3d7b3``). If
absent (offline / un-migrated env) that test skips cleanly, matching the
P0/P1 infra-limited-test convention. The pure-GUC checkin-isolation test needs no
role and always runs.

Runs against ``async_engine`` — the migrated dev DB where the ``meli_app`` role +
RLS policies actually exist (the ``db_session`` fixture builds schema via
``Base.metadata.create_all``, which never emits RLS/policy/role statements).
"""
import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from app.database import _reset_rls_context, _reset_rls_on_checkin, engine

_SENTINEL = str(uuid.uuid4())
_READ_GUC = text("SELECT current_setting('app.current_user_id', true)")
_SET_GUC = text("SELECT set_config('app.current_user_id', :u, false)")
_PID = text("SELECT pg_backend_pid()")
_COUNT_REPORTS = text("SELECT count(*) FROM reports")


async def _role_missing(conn) -> bool:
    exists = (
        await conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'meli_app'"))
    ).scalar()
    return exists is None


async def _guc(conn):
    return (await conn.execute(_READ_GUC)).scalar()


async def _pid(conn):
    return (await conn.execute(_PID)).scalar()


def test_checkin_listener_is_registered_symmetric_to_checkout():
    """Both ends of the pool cycle must reset the RLS GUC (Decision 7).

    Asserts the NEW ``checkin`` listener is wired symmetrically to the
    pre-existing ``checkout`` listener on ``engine.sync_engine``.
    """
    assert event.contains(engine.sync_engine, "checkout", _reset_rls_context), (
        "pre-existing checkout reset must stay registered"
    )
    assert event.contains(engine.sync_engine, "checkin", _reset_rls_on_checkin), (
        "B10 must add a symmetric checkin reset listener"
    )


@pytest.mark.asyncio
async def test_pooled_connection_fails_closed_and_does_not_leak(async_engine):
    """Raw pooled connection: blank GUC → RLS SELECT fails closed; no cross-request leak."""
    async with async_engine.connect() as conn:
        if await _role_missing(conn):
            pytest.skip("meli_app role not present in this environment")

        # (A) A freshly checked-out pooled connection observes a BLANK GUC — the
        #     checkout reset ran; nothing was inherited from a prior request.
        assert await _guc(conn) in (None, ""), "checkout must leave the GUC blank"

        # (B) Under meli_app (BYPASSRLS off) an RLS-table SELECT with the blank
        #     GUC FAILS CLOSED: ''::uuid raises rather than exposing rows.
        try:
            await conn.execute(text("SET ROLE meli_app"))
            with pytest.raises(DBAPIError) as exc:
                await conn.execute(_COUNT_REPORTS)
            assert "uuid" in str(exc.value).lower()
            await conn.rollback()  # clear the aborted transaction
        finally:
            # Never return a meli_app-roled connection to the shared pool.
            await conn.execute(text("RESET ROLE"))

        # (C) Simulate a request: set the GUC session-scoped, commit, then let the
        #     connection return to the pool on ``async with`` exit (checkin fires).
        await conn.execute(_SET_GUC.bindparams(u=_SENTINEL))
        assert await _guc(conn) == _SENTINEL, "GUC set is visible within the connection"
        await conn.commit()

    # (D) The NEXT checkout must see a BLANK GUC — the sentinel must not leak
    #     across pooled requests (checkin + checkout reset).
    async with async_engine.connect() as conn2:
        assert await _guc(conn2) in (None, ""), (
            "GUC must not leak from a prior request across the pool"
        )
        assert await _guc(conn2) != _SENTINEL


@pytest.mark.asyncio
async def test_checkin_listener_resets_guc_in_isolation(async_engine):
    """With the checkout listener DETACHED, the checkin listener alone blanks the GUC.

    Proves the new checkin reset does real work (defense-in-depth), independent of
    the pre-existing checkout reset. Forces reuse of the same physical connection
    via ``pg_backend_pid()`` so the assertion targets the connection that actually
    carried the sentinel.
    """
    # Detach the checkout reset so ONLY the checkin listener can blank the GUC.
    event.remove(async_engine.sync_engine, "checkout", _reset_rls_context)
    held = []
    try:
        # Set the sentinel on a connection, note its backend pid, return it.
        async with async_engine.connect() as conn:
            target_pid = await _pid(conn)
            await conn.execute(_SET_GUC.bindparams(u=_SENTINEL))
            await conn.commit()
        # conn returned to the pool -> checkin listener must have reset the GUC.

        # Re-acquire connections (holding them) until we get target_pid back,
        # forcing reuse of the connection that carried the sentinel. Bounded by
        # the pool ceiling (pool_size + max_overflow = 10) so it never blocks.
        reused = None
        for _ in range(10):
            c = await async_engine.connect()
            held.append(c)
            if await _pid(c) == target_pid:
                reused = c
                break

        if reused is None:
            pytest.skip("could not force pooled-connection reuse to isolate checkin")

        value = await _guc(reused)
        assert value in (None, ""), (
            f"checkin listener must blank the GUC on return, but saw {value!r}"
        )
        assert value != _SENTINEL
    finally:
        for c in held:
            await c.close()
        # Restore the pre-existing checkout reset for the rest of the suite.
        event.listen(async_engine.sync_engine, "checkout", _reset_rls_context)
