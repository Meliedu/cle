"""Import a bank into an environment and publish it, as the API would.

Mirrors ``POST /api/admin/placement/versions/{id}/publish`` rather than
reimplementing it: same preflight gate, same single-published-version rule,
same audit event with a named instructor as actor. The endpoint needs an
authenticated session, which a batch run does not have, so the actor is named
explicitly on the command line and recorded the same way.

Publishing makes the test live. With ``window_opens_at``/``window_closes_at``
null it is open immediately to every eligible learner, so this refuses to run
without ``--confirm``.

    python scripts/publish_placement_version.py --actor lcmeli@ust.hk --dry-run
    python scripts/publish_placement_version.py --actor lcmeli@ust.hk --confirm
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.placement import PlacementTestVersion  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import placement as svc  # noqa: E402
from app.services import placement_bank  # noqa: E402

DEFAULT_BANK = placement_bank.BANK_DIR / "meli-placement-v1.3.json"
SCORING_RULE_VERSION = "v1.3-candidate"


async def run(args: argparse.Namespace) -> int:
    bank = placement_bank.load_bank_file(Path(args.bank))
    version_code = bank["version_code"]

    file_check = placement_bank.preflight_bank(bank)
    print(f"bank preflight: {'PASS' if file_check.can_publish else 'FAIL'} "
          f"({len(file_check.blocking)} blocking, "
          f"{len(file_check.findings) - len(file_check.blocking)} advisory)")
    if not file_check.can_publish:
        for finding in file_check.blocking:
            print(f"  [blocking] {finding.code} {finding.form_code} {finding.detail}")
        return 1

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            actor = (
                await db.execute(select(User).where(User.email == args.actor))
            ).scalar_one_or_none()
            if actor is None:
                print(f"no user {args.actor!r} in this database", file=sys.stderr)
                return 1
            if actor.role != "instructor":
                print(f"{args.actor} is {actor.role}, not an instructor", file=sys.stderr)
                return 1

            already = (
                await db.execute(
                    select(PlacementTestVersion).where(
                        PlacementTestVersion.status == "published"
                    )
                )
            ).scalar_one_or_none()
            if already is not None:
                print(
                    f"REFUSING: '{already.version_code}' is already published. "
                    "Retire it first; only one version may be live.",
                    file=sys.stderr,
                )
                return 1

            existing = (
                await db.execute(
                    select(PlacementTestVersion).where(
                        PlacementTestVersion.version_code == version_code
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                if args.dry_run:
                    print(f"would import {version_code} as candidate, then publish it")
                    print(f"would record published_by = {actor.email}")
                    return 0
                version = await placement_bank.import_bank(
                    db,
                    bank,
                    scoring_rule_version=SCORING_RULE_VERSION,
                    source_package=bank.get("source_package"),
                )
                print(f"imported {version_code} as candidate")
            else:
                version = existing
                print(f"{version_code} already imported (status={version.status})")
                if args.dry_run:
                    print("would publish it")
                    return 0

            stored = await placement_bank.preflight_version(db, version)
            print(f"stored-rows preflight: {'PASS' if stored.can_publish else 'FAIL'} "
                  f"({len(stored.blocking)} blocking)")
            if not stored.can_publish:
                for finding in stored.blocking:
                    print(f"  [blocking] {finding.code} {finding.form_code} {finding.detail}")
                await db.rollback()
                return 1

            version.status = "published"
            version.published_by = actor.id
            version.published_at = datetime.now(timezone.utc)
            await db.flush()

            await svc.record_audit(
                db,
                actor=actor,
                actor_role="instructor",
                event_type="placement.version.published",
                entity_kind="placement_test_version",
                entity_id=version.id,
                metadata={
                    "version_code": version.version_code,
                    "key_version": version.key_version,
                    "advisory_findings": len(stored.findings),
                    "published_via": "scripts/publish_placement_version.py",
                },
            )
            await db.commit()
            print(
                f"\nPUBLISHED {version.version_code} (published_by={actor.email}).\n"
                f"Windows are open-ended, so the test is live to eligible learners now."
            )
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", default=str(DEFAULT_BANK))
    parser.add_argument("--actor", required=True, help="instructor email to record as publisher")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm", action="store_true", help="required to actually publish")
    args = parser.parse_args()

    if not args.dry_run and not args.confirm:
        print(
            "REFUSING: --confirm not given. Publishing makes a scored placement "
            "test live to learners immediately.",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
