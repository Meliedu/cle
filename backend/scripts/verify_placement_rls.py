"""Prove the placement RLS policies behave, under a role that cannot bypass them.

The app connects as a BYPASSRLS role today, so these policies are inert in
production and would rot unnoticed. This runs the real queries through a
throwaway non-superuser role against the migrated database, so what is checked
is behaviour rather than the SQL text.

    python scripts/verify_placement_rls.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg  # noqa: E402

from app.config import settings  # noqa: E402

ROLE = "placement_rls_probe"
TABLES = ("placement_attempts", "placement_responses")

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{f' :: {detail}' if detail else ''}")
    if not ok:
        failures.append(name)


def _dsn() -> str:
    return str(settings.database_url).replace("postgresql+asyncpg://", "postgresql://")


async def main() -> int:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(f"DROP ROLE IF EXISTS {ROLE}")
        await conn.execute(f"CREATE ROLE {ROLE} NOLOGIN")
        for table in TABLES:
            await conn.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {ROLE}")

        # A real attempt to read: owner, stranger and reviewer.
        row = await conn.fetchrow(
            "SELECT id, user_id FROM placement_attempts ORDER BY created_at DESC LIMIT 1"
        )
        if row is None:
            print("no placement attempts in this database; nothing to probe")
            return 0
        attempt_id, owner_id = row["id"], row["user_id"]
        stranger = uuid.uuid4()

        async def visible(user_id, role) -> int:
            async with conn.transaction():
                await conn.execute(f'SET LOCAL ROLE "{ROLE}"')
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, true)", str(user_id)
                )
                await conn.execute(
                    "SELECT set_config('app.current_user_role', $1, true)", role
                )
                n = await conn.fetchval(
                    "SELECT count(*) FROM placement_attempts WHERE id = $1", attempt_id
                )
                await conn.execute("RESET ROLE")
            return int(n)

        check("the owner sees their own attempt", await visible(owner_id, "student") == 1)
        check("a stranger sees nothing", await visible(stranger, "student") == 0)
        check(
            "a reviewer can read someone else's attempt",
            await visible(stranger, "instructor") == 1,
            "this is the case owner-isolation alone gets wrong, silently",
        )
        check("a blank role is not a reviewer", await visible(stranger, "") == 0)

        # A reviewer reads; they never rewrite what a learner answered.
        wrote = None
        try:
            async with conn.transaction():
                await conn.execute(f'SET LOCAL ROLE "{ROLE}"')
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, true)", str(stranger)
                )
                await conn.execute(
                    "SELECT set_config('app.current_user_role', 'instructor', true)"
                )
                await conn.execute(
                    "UPDATE placement_attempts SET raw_score = 99 WHERE id = $1",
                    attempt_id,
                )
                wrote = True
        except asyncpg.PostgresError:
            wrote = False
        # An UPDATE with no matching row under RLS silently affects zero rows
        # rather than raising, so confirm the value is untouched either way.
        after = await conn.fetchval(
            "SELECT raw_score FROM placement_attempts WHERE id = $1", attempt_id
        )
        check(
            "a reviewer cannot rewrite a learner's answers",
            after != 99,
            f"raw_score is {after}, update {'raised' if wrote is False else 'affected no rows'}",
        )
    finally:
        for table in TABLES:
            await conn.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
        await conn.execute(f"DROP ROLE IF EXISTS {ROLE}")
        await conn.close()

    print()
    if failures:
        print(f"{len(failures)} RLS check(s) failed: {', '.join(failures)}")
        return 1
    print("PASS: placement RLS behaves correctly under a non-BYPASSRLS role.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
