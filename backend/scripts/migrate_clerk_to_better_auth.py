"""Clerk → Better Auth user migration.

Walks every row in ``public.users`` whose ``better_auth_id`` is NULL,
creates a matching ``auth.user`` row (Better Auth's user table), and
links them by setting ``public.users.better_auth_id``. The local UUID
on ``public.users.id`` is preserved untouched, which means every FK that
points at it (courses, documents, enrollments, canvas_user_credentials,
quiz_folders, flashcard_folders, api_usage, scheduler_models, …) keeps
resolving — no content is touched, only the auth-provider pointer
changes.

Idempotent — reruns skip rows that already have ``better_auth_id`` set.

Passwords are NOT transferred. Clerk's Backend API does not return hashes
in the normal user GET endpoint, and even when an export is obtained the
hash format only round-trips cleanly when both sides use the same
algorithm. We side-step the whole risk window by:

  1. Marking each migrated ``auth.user`` as ``emailVerified = true`` so
     they aren't blocked behind a verification step (we trust Clerk's
     prior verification).
  2. Telling users at the cutover that they need to set a new password
     via the standard "Forgot password?" flow on /sign-in. Users who
     signed in through a social provider (e.g. Microsoft) re-link by
     email automatically on their next sign-in attempt.

Usage::

    cd backend
    .venv/bin/python -m scripts.migrate_clerk_to_better_auth --dry-run
    .venv/bin/python -m scripts.migrate_clerk_to_better_auth --live
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import secrets
import sys
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory

logger = logging.getLogger("clerk_to_better_auth")


@dataclass(frozen=True)
class Candidate:
    """One unmigrated row from public.users."""

    user_id: str
    email: str
    full_name: str | None
    avatar_url: str | None


@dataclass(frozen=True)
class Outcome:
    candidate: Candidate
    better_auth_id: str
    note: str  # "linked-existing" | "created-and-linked"


async def _candidates(session: AsyncSession) -> list[Candidate]:
    rows = await session.execute(
        text(
            """
            SELECT id::text AS user_id,
                   lower(email) AS email,
                   full_name,
                   avatar_url
              FROM public.users
             WHERE better_auth_id IS NULL
             ORDER BY created_at
            """
        )
    )
    return [Candidate(**dict(row._mapping)) for row in rows]


async def _existing_auth_user_id(
    session: AsyncSession, email: str
) -> str | None:
    """If Better Auth already has a user for this email, reuse its id."""
    result = await session.execute(
        text("SELECT id FROM auth.user WHERE lower(email) = lower(:email)"),
        {"email": email},
    )
    row = result.first()
    return row[0] if row else None


async def _insert_auth_user(
    session: AsyncSession,
    *,
    email: str,
    name: str | None,
    image: str | None,
) -> str:
    """Create a fresh row in auth.user and return its id."""
    new_id = secrets.token_urlsafe(16)
    await session.execute(
        text(
            """
            INSERT INTO auth.user
                (id, email, "emailVerified", name, image, "createdAt", "updatedAt")
            VALUES
                (:id, :email, true, :name, :image, now(), now())
            """
        ),
        {
            "id": new_id,
            "email": email,
            "name": name or email.split("@")[0],
            "image": image,
        },
    )
    return new_id


async def _link_local(session: AsyncSession, user_id: str, better_auth_id: str) -> None:
    await session.execute(
        text(
            """
            UPDATE public.users
               SET better_auth_id = :better_auth_id
             WHERE id = :user_id
            """
        ),
        {"better_auth_id": better_auth_id, "user_id": user_id},
    )


async def _migrate_one(
    session: AsyncSession, candidate: Candidate, *, dry_run: bool
) -> Outcome:
    existing = await _existing_auth_user_id(session, candidate.email)
    if existing is not None:
        if not dry_run:
            await _link_local(session, candidate.user_id, existing)
        return Outcome(candidate, existing, "linked-existing")

    if dry_run:
        return Outcome(candidate, "<would-create>", "created-and-linked")

    new_id = await _insert_auth_user(
        session,
        email=candidate.email,
        name=candidate.full_name,
        image=candidate.avatar_url,
    )
    await _link_local(session, candidate.user_id, new_id)
    return Outcome(candidate, new_id, "created-and-linked")


async def run(*, dry_run: bool) -> int:
    async with async_session_factory() as session:
        candidates = await _candidates(session)
        if not candidates:
            print("Nothing to migrate — every public.users row already has better_auth_id.")
            return 0

        mode = "DRY RUN" if dry_run else "LIVE"
        print(f"\n=== Clerk → Better Auth migration [{mode}] ===")
        print(f"Candidates: {len(candidates)}\n")

        outcomes: list[Outcome] = []
        for candidate in candidates:
            try:
                outcome = await _migrate_one(session, candidate, dry_run=dry_run)
                outcomes.append(outcome)
                print(
                    f"  · {candidate.email:<40s} → {outcome.note:<22s} "
                    f"better_auth_id={outcome.better_auth_id}"
                )
            except Exception as exc:
                print(f"  ! {candidate.email:<40s} FAILED: {exc}")
                if not dry_run:
                    await session.rollback()
                    return 1

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

        # Summary
        created = sum(1 for o in outcomes if o.note == "created-and-linked")
        linked = sum(1 for o in outcomes if o.note == "linked-existing")
        print(
            f"\n  Created auth.user rows: {created}\n"
            f"  Linked to existing rows: {linked}\n"
            f"  Total processed:         {len(outcomes)}"
        )
        if dry_run:
            print(
                "\nNo changes committed. Re-run with --live to apply.\n"
                "After --live: tell users to use 'Forgot password?' on /sign-in\n"
                "to set a new password (Clerk hashes are not transferred)."
            )
        else:
            print(
                "\nMigration committed. Next steps:\n"
                "  1. Email migrated users with the cutover notice + reset link.\n"
                "  2. Verify on /dashboard that content is intact.\n"
                "  3. Proceed to Phase 5 (decommission Clerk)."
            )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen, commit nothing.",
    )
    group.add_argument(
        "--live",
        action="store_true",
        help="Actually perform the migration. Idempotent.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    return asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
