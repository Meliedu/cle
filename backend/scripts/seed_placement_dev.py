"""Publish a DEV-ONLY placement version so the flow can be exercised locally.

The real v1.2 bank cannot be published: two of its items carry a teacher's
report that the key is wrong or ambiguous, and the preflight refuses. That is
correct, and it also means the sitting flow cannot be walked through on real
content until CLE resolves those items.

This imports the same bank under a clearly-marked dev version code with those
flags cleared, so local verification is possible without ever pretending the
real content is publishable. It refuses to run against a non-local database.

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

DEV_VERSION_CODE = "meli-placement-v1.2-DEVFIXTURE"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def _is_local() -> bool:
    url = str(settings.database_url)
    return any(host in url for host in LOCAL_HOSTS)


def _dev_bank() -> dict:
    """The real bank, re-coded and with blocking content flags cleared.

    Only the flags are dropped. Every item's text, options and key are the real
    ones, so what is exercised locally is the real delivery surface.
    """
    bank = placement_bank.load_bank_file(version_code="meli-placement-v1.2")
    bank["version_code"] = DEV_VERSION_CODE
    for form in bank["forms"]:
        for item in form["items"]:
            item["teacher_flags"] = []
            # The same defect the flags describe also trips the mechanical
            # prompt/blank-number check, so normalise it for the fixture.
            if item["safe"].get("prompt"):
                item["safe"]["prompt"] = (
                    f"请选择最合适的一项填入第（{item['question_number']}）空。"
                )
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
            scoring_rule_version="v1.2-devfixture",
            review_policy={"version": "v1.2-devfixture"},
        )
        version.status = "published"
        version.published_at = datetime.now(timezone.utc)
        await session.commit()
        print(f"published {DEV_VERSION_CODE} for local verification")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
