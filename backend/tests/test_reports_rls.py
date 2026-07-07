"""RLS owner-isolation enforcement test for ``reports`` (P7 Task B7).

The student-audience rows of ``reports`` are owner-owned (Decision 2). The
migration (``a1f3c8d5b2e7``) enables ROW LEVEL SECURITY and an owner-isolation
policy keyed on the ``app.current_user_id`` GUC (COPIED verbatim from
``d94257fc717c`` / ``readiness_responses``):

    USING      (user_id = current_setting('app.current_user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)

This test proves the policy is *enforced* (not merely declared) by running under
the non-superuser ``meli_app`` role (no ``BYPASSRLS``; ``postgres`` has it),
mirroring ``tests/test_readiness_rls.py`` / ``test_work_item_progress_rls.py``.
It runs against ``async_engine`` — the migrated dev DB where the policy actually
exists — because the ``db_session`` fixture builds schema via
``Base.metadata.create_all``, which never emits RLS/policy statements.

Skip-guard: if the ``meli_app`` role is absent (offline / un-migrated env) the
test skips cleanly, matching the P0/P1 infra-limited-test convention.

Because ``async_engine`` is the SHARED dev DB (not the disposable test DB), all
seed rows are torn down in a ``finally`` even on assertion failure. A
teacher-audience row (``user_id = NULL``) is never created here — the policy can
never match ``NULL = GUC``, so those rows are structurally invisible to every
student and are covered by the endpoint-guard tests instead.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

# ---------------------------------------------------------------------------
# Raw SQL helpers (superuser seed / teardown; policy assertions run as meli_app)
# ---------------------------------------------------------------------------

_INSERT_USER = text(
    "INSERT INTO users (id, better_auth_id, email, role) "
    "VALUES (CAST(:id AS uuid), :ba, :email, :role)"
)
_INSERT_COURSE = text(
    "INSERT INTO courses (id, name, language, instructor_id, enroll_code, settings) "
    "VALUES (CAST(:id AS uuid), :name, :language, CAST(:instructor_id AS uuid), :enroll_code, '{}'::jsonb)"
)
_INSERT_REPORT = text(
    "INSERT INTO reports "
    "(id, course_id, audience, user_id, period, period_start, period_end, status) "
    "VALUES (CAST(:id AS uuid), CAST(:c AS uuid), 'student', CAST(:u AS uuid), "
    "'weekly', now(), now(), 'sent')"
)
_SET_GUC = text("SELECT set_config('app.current_user_id', :u, false)")
_COUNT = text("SELECT count(*) FROM reports")


async def _role_missing(conn) -> bool:
    exists = (
        await conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'meli_app'")
        )
    ).scalar()
    return exists is None


@pytest.mark.asyncio
async def test_reports_rls_owner_isolation(async_engine):
    """User A's report row is invisible + immutable to user B under RLS.

    Proves, under ``meli_app`` (BYPASSRLS off):
      * A (GUC=A) inserts a row and sees exactly its own row.
      * B (GUC=B) SELECT returns nothing (row hidden).
      * B UPDATE / DELETE of A's row affect 0 rows (row invisible → no-op).
      * B INSERT with ``user_id = A`` is rejected by the ``WITH CHECK`` clause.
      * Switching the GUC back to A within the SAME connection restores
        visibility — proving the policy reads the *live* GUC value (the pooled-
        connection concern).
      * A blank GUC (RESET) fails CLOSED — the ``''::uuid`` cast errors rather
        than exposing rows.
    """
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    instructor = str(uuid.uuid4())
    course_id = str(uuid.uuid4())
    row_a = str(uuid.uuid4())
    suffix = uuid.uuid4().hex[:6].upper()

    async with async_engine.connect() as conn:
        if await _role_missing(conn):
            pytest.skip("meli_app role not present in this environment")

        # -- Seed prerequisite rows as the superuser (FKs) then commit so they
        #    survive the rollbacks used below to clear expected-error tx aborts.
        try:
            await conn.execute(
                _INSERT_USER.bindparams(
                    id=user_a, ba=f"rls_rpt_a_{suffix}", email=f"rls_rpt_a_{suffix}@connect.ust.hk", role="student"
                )
            )
            await conn.execute(
                _INSERT_USER.bindparams(
                    id=user_b, ba=f"rls_rpt_b_{suffix}", email=f"rls_rpt_b_{suffix}@connect.ust.hk", role="student"
                )
            )
            await conn.execute(
                _INSERT_USER.bindparams(
                    id=instructor, ba=f"rls_rpt_i_{suffix}", email=f"rls_rpt_i_{suffix}@ust.hk", role="instructor"
                )
            )
            await conn.execute(
                _INSERT_COURSE.bindparams(
                    id=course_id, name="RLS Report Probe", language="zh",
                    instructor_id=instructor, enroll_code=f"RPR{suffix}",
                )
            )
            await conn.commit()

            # -- Drop to the non-superuser app role: RLS is now enforced.
            await conn.execute(text("SET ROLE meli_app"))

            # Act as user A: insert own row, confirm own visibility.
            await conn.execute(_SET_GUC.bindparams(u=user_a))
            await conn.execute(
                _INSERT_REPORT.bindparams(id=row_a, u=user_a, c=course_id)
            )
            assert (await conn.execute(_COUNT)).scalar() == 1

            # Switch to user B: A's row must vanish + be immutable.
            await conn.execute(_SET_GUC.bindparams(u=user_b))
            assert (await conn.execute(_COUNT)).scalar() == 0

            upd = await conn.execute(
                text("UPDATE reports SET status = 'archived' WHERE user_id = CAST(:u AS uuid)").bindparams(u=user_a)
            )
            assert upd.rowcount == 0, "B must not be able to UPDATE A's row"

            dele = await conn.execute(
                text("DELETE FROM reports WHERE user_id = CAST(:u AS uuid)").bindparams(u=user_a)
            )
            assert dele.rowcount == 0, "B must not be able to DELETE A's row"

            # Back to A within the SAME connection: row is untouched + visible.
            # Proves the policy reads the *live* GUC and B's ops were true no-ops.
            await conn.execute(_SET_GUC.bindparams(u=user_a))
            assert (await conn.execute(_COUNT)).scalar() == 1

            # Commit locks in SET ROLE (meli_app), the GUC (session-level,
            # is_local=false) and A's row, so the deliberate errors below can be
            # rolled back without losing the meli_app context.
            await conn.commit()

            # B cannot INSERT a row it doesn't own: WITH CHECK rejects it.
            await conn.execute(_SET_GUC.bindparams(u=user_b))
            with pytest.raises(DBAPIError) as check_exc:
                await conn.execute(
                    _INSERT_REPORT.bindparams(id=str(uuid.uuid4()), u=user_a, c=course_id)
                )
            await conn.rollback()  # clear the aborted tx (reverts to committed state)
            assert "row-level security" in str(check_exc.value).lower()

            # Pooled-connection / reset probe: a blank GUC fails CLOSED. RESET
            # leaves the GUC as '' (empty string, not NULL); ''::uuid raises, so
            # a stale/blank connection ERRORS instead of exposing rows.
            await conn.execute(text("RESET app.current_user_id"))
            with pytest.raises(DBAPIError) as reset_exc:
                await conn.execute(_COUNT)
            await conn.rollback()
            assert "uuid" in str(reset_exc.value).lower()

        finally:
            # Teardown on the SHARED dev DB. Reset to superuser first (postgres
            # has BYPASSRLS) so cleanup sees every row regardless of the GUC.
            await conn.rollback()
            await conn.execute(text("RESET ROLE"))
            await conn.execute(
                text(
                    "DELETE FROM reports "
                    "WHERE user_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
                ).bindparams(a=user_a, b=user_b)
            )
            await conn.execute(
                text("DELETE FROM courses WHERE id = CAST(:c AS uuid)").bindparams(c=course_id)
            )
            await conn.execute(
                text(
                    "DELETE FROM users "
                    "WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid), CAST(:i AS uuid))"
                ).bindparams(a=user_a, b=user_b, i=instructor)
            )
            await conn.commit()
