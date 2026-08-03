"""Publish a DEV-ONLY placement version so the flow can be exercised locally.

Under v1.2 this existed because the real bank *could not* be published: two of
its items carried a teacher's report that the key was wrong or ambiguous, and
the preflight refused. v1.3 revised those items, so the real bank now preflights
clean and the reason has changed rather than disappeared.

What remains is that publishing the real version is a deliberate, audited,
instructor-gated act which also retires whatever is live, and only one version
may be published at a time. A developer walking the sitting flow should not have
to perform that act, and must not leave a local machine's idea of "the published
placement test" pointing at a version nobody at CLE released. So this imports
the same content under a clearly-marked dev version code and publishes that
instead. It refuses to run against a non-local database.

    python scripts/seed_placement_dev.py
    python scripts/seed_placement_dev.py --remove
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.models.placement import PlacementTestVersion  # noqa: E402
from app.services import placement_bank  # noqa: E402

DEV_VERSION_CODE = "meli-placement-v1.3-DEVFIXTURE"
BANK_VERSION = "meli-placement-v1.3"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def _is_local() -> bool:
    url = str(settings.database_url)
    return any(host in url for host in LOCAL_HOSTS)


def _dev_bank() -> dict:
    """The real bank under a dev version code, otherwise untouched.

    v1.3 needs no doctoring: it preflights clean, so every item's text, options
    and key are exactly the real ones and what is exercised locally is the real
    delivery surface. Only the version code differs, and the preflight below
    still runs -- if a future package regresses, this script must fail rather
    than quietly seed content the gate would have refused.
    """
    bank = placement_bank.load_bank_file(version_code=BANK_VERSION)
    bank["version_code"] = DEV_VERSION_CODE
    return bank


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args(argv)

    if not _is_local():
        print("refusing to run: DATABASE_URL is not local")
        return 2

    async with async_session_factory() as session:
        existing = (
            await session.execute(
                select(PlacementTestVersion).where(
                    PlacementTestVersion.version_code == DEV_VERSION_CODE
                )
            )
        ).scalar_one_or_none()

        if args.remove:
            if existing is None:
                print("nothing to remove")
                return 0
            await session.execute(
                delete(PlacementTestVersion).where(
                    PlacementTestVersion.id == existing.id
                )
            )
            await session.commit()
            print(f"removed {DEV_VERSION_CODE}")
            return 0

        if existing is not None:
            print(f"{DEV_VERSION_CODE} already exists ({existing.status})")
            return 0

        bank = _dev_bank()
        result = placement_bank.preflight_bank(bank)
        if not result.can_publish:
            print("dev fixture still has blocking findings:")
            for finding in result.blocking:
                print(f"  {finding.code}: {finding.detail}")
            return 1

        version = await placement_bank.import_bank(
            session,
            bank,
            scoring_rule_version="v1.3-devfixture",
            review_policy={"version": "v1.3-devfixture"},
        )
        version.status = "published"
        version.published_at = datetime.now(timezone.utc)
        await session.commit()
        print(f"published {DEV_VERSION_CODE} for local verification")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
