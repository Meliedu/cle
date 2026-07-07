"""RLS owner-isolation enforcement test for ``activity_responses`` (P5 Task B12).

``activity_responses`` is a P5 student-owned table (Decision 3). Its migration
enables ROW LEVEL SECURITY and an owner-isolation policy (``activity_responses_
owner_isolation``) keyed on the ``app.current_user_id`` GUC (copied verbatim from
the ``work_item_progress`` / ``checkpoint_responses`` precedent):

    USING      (user_id = current_setting('app.current_user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)

This test proves the policy is *enforced* (not merely declared) by running under
the non-superuser ``meli_app`` role (no ``BYPASSRLS``; ``postgres`` has it),
mirroring the ``tests/test_work_item_progress_rls.py`` precedent. It runs against
``async_engine`` — the migrated dev DB where the policy actually exists — because
the ``db_session`` fixture builds schema via ``Base.metadata.create_all``, which
never emits RLS/policy statements.

Skip-guard: if the ``meli_app`` role is absent (offline / un-migrated env) the
test skips cleanly, matching the P0/P1 infra-limited-test convention.

Because ``async_engine`` is the SHARED dev DB (not the disposable test DB), all
seed rows are torn down in a ``finally`` even on assertion failure.

The operational parent (``activities``) is deliberately NO-RLS (endpoint-guarded)
— here it is only seeded as the FK parent of a response row.
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
_INSERT_ACTIVITY = text(
    "INSERT INTO activities "
    "(id, course_id, format, title, status) "
    "VALUES (CAST(:id AS uuid), CAST(:c AS uuid), 'swipe', "
    "'RLS Probe Activity', 'published')"
)
_INSERT_RESPONSE = text(
    "INSERT INTO activity_responses "
    "(id, activity_id, user_id, status) "
    "VALUES (CAST(:id AS uuid), CAST(:a AS uuid), CAST(:u AS uuid), 'on_time')"
)
_SET_GUC = text("SELECT set_config('app.current_user_id', :u, false)")
_COUNT = text("SELECT count(*) FROM activity_responses")


async def _role_missing(conn) -> bool:
    exists = (
        await conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'meli_app'")
        )
    ).scalar()
    return exists is None


@pytest.mark.asyncio
async def test_activity_responses_rls_owner_isolation(async_engine):
    """User A's response row is invisible + immutable to user B under RLS.

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
    activity_id = str(uuid.uuid4())
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
                    id=user_a, ba=f"rls_a_{suffix}", email=f"rls_a_{suffix}@connect.ust.hk", role="student"
                )
            )
            await conn.execute(
                _INSERT_USER.bindparams(
                    id=user_b, ba=f"rls_b_{suffix}", email=f"rls_b_{suffix}@connect.ust.hk", role="student"
                )
            )
            await conn.execute(
                _INSERT_USER.bindparams(
                    id=instructor, ba=f"rls_i_{suffix}", email=f"rls_i_{suffix}@ust.hk", role="instructor"
                )
            )
            await conn.execute(
                _INSERT_COURSE.bindparams(
                    id=course_id, name="RLS Probe", language="zh",
                    instructor_id=instructor, enroll_code=f"RLS{suffix}",
                )
            )
            await conn.execute(
                _INSERT_ACTIVITY.bindparams(id=activity_id, c=course_id)
            )
            await conn.commit()

            # -- Drop to the non-superuser app role: RLS is now enforced.
            await conn.execute(text("SET ROLE meli_app"))

            # Act as user A: insert own row, confirm own visibility.
            await conn.execute(_SET_GUC.bindparams(u=user_a))
            await conn.execute(
                _INSERT_RESPONSE.bindparams(id=row_a, a=activity_id, u=user_a)
            )
            assert (await conn.execute(_COUNT)).scalar() == 1

            # Switch to user B: A's row must vanish + be immutable.
            await conn.execute(_SET_GUC.bindparams(u=user_b))
            assert (await conn.execute(_COUNT)).scalar() == 0

            upd = await conn.execute(
                text("UPDATE activity_responses SET status = 'late' WHERE user_id = CAST(:u AS uuid)").bindparams(u=user_a)
            )
            assert upd.rowcount == 0, "B must not be able to UPDATE A's row"

            dele = await conn.execute(
                text("DELETE FROM activity_responses WHERE user_id = CAST(:u AS uuid)").bindparams(u=user_a)
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
                    _INSERT_RESPONSE.bindparams(
                        id=str(uuid.uuid4()), a=activity_id, u=user_a
                    )
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
                    "DELETE FROM activity_responses "
                    "WHERE user_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
                ).bindparams(a=user_a, b=user_b)
            )
            await conn.execute(
                text("DELETE FROM activities WHERE id = CAST(:a AS uuid)").bindparams(a=activity_id)
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
