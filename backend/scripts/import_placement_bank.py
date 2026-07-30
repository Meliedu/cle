"""Import a placement item bank into the database as a candidate version.

    python scripts/import_placement_bank.py                    # import v1.2
    python scripts/import_placement_bank.py --preflight-only   # just report

Import never publishes. The version lands as ``candidate`` and a separate,
audited, instructor-gated action promotes it, so content that has not been
signed off cannot be sat by a learner.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session_factory  # noqa: E402
from app.services import placement_bank  # noqa: E402

DEFAULT_VERSION = "meli-placement-v1.2"
SCORING_RULE_VERSION = "v1.2-candidate"

#: Thresholds recorded with the version so an attempt scored today keeps its
#: rules even if CLE tunes them after pilot data arrives.
REVIEW_POLICY = {
    "version": "v1.2-candidate",
    "band_minimum": 3,
    "cumulative_threshold": 0.7,
    "incomplete_answers_below": 27,
    "fast_duration_minutes": 12,
    "long_duration_minutes": 45,
    "background_mismatch_bands": 1,
    "attempt_spread_bands": 1,
}


def _report(result: placement_bank.PreflightResult) -> None:
    blocking = result.blocking
    advisory = [f for f in result.findings if f.severity == "advisory"]
    print(f"preflight for {result.version_code}: ", end="")
    print("PASS" if result.can_publish else f"BLOCKED ({len(blocking)} issue(s))")
    for finding in (*blocking, *advisory):
        where = ""
        if finding.form_code:
            where = f" Form {finding.form_code}"
            if finding.question_number:
                where += f" Q{finding.question_number}"
            if finding.external_item_id:
                where += f" ({finding.external_item_id})"
        print(f"  [{finding.severity}] {finding.code}{where}: {finding.detail}")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-code", default=DEFAULT_VERSION)
    parser.add_argument("--file", type=Path, default=None)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="report blocking issues without writing anything",
    )
    args = parser.parse_args(argv)

    bank = placement_bank.load_bank_file(args.file, version_code=args.version_code)
    result = placement_bank.preflight_bank(bank)
    _report(result)

    if args.preflight_only:
        return 0 if result.can_publish else 1

    async with async_session_factory() as session:
        try:
            version = await placement_bank.import_bank(
                session,
                bank,
                scoring_rule_version=SCORING_RULE_VERSION,
                review_policy=REVIEW_POLICY,
            )
        except placement_bank.PlacementBankError as error:
            print(f"import failed: {error.code}: {error.message}")
            return 1
        await session.commit()
        items = await placement_bank.count_items(session, version.id)

    print(
        f"imported {version.version_code} as '{version.status}' "
        f"({items} items, key version {version.key_version})"
    )
    if not result.can_publish:
        print(
            "NOT publishable yet: resolve the blocking findings above, then "
            "POST /api/placement/versions/{id}/publish"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
