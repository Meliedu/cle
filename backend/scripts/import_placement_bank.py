"""Import a placement item bank into the database as a candidate version.

    python scripts/import_placement_bank.py                    # import v1.3
    python scripts/import_placement_bank.py --preflight-only   # just report

Import never publishes. The version lands as ``candidate`` and a separate,
audited, instructor-gated action promotes it, so content that has not been
signed off cannot be sat by a learner. That separation matters more in v1.3
than it did in v1.2: v1.2 was held back by a blocking content defect, whereas
v1.3 preflights clean, and the only thing standing between import and delivery
is a human deciding the teacher re-review is finished.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session_factory  # noqa: E402
from app.services import placement_bank, placement_scoring  # noqa: E402

DEFAULT_VERSION = "meli-placement-v1.3"
SCORING_RULE_VERSION = "v1.3-candidate"

#: Thresholds recorded with the version so an attempt scored today keeps its
#: rules even if CLE tunes them after pilot data arrives.
#:
#: Every value is unchanged from v1.2: the v1.3 workbook's "Rules & Mapping"
#: sheet carries the same numbers, and only the version label moved. Recording
#: them again rather than aliasing v1.2 keeps each version's policy readable on
#: its own, which is the point of versioning them at all.
REVIEW_POLICY = {
    "version": "v1.3-candidate",
    "band_minimum": 3,
    "cumulative_threshold": 0.7,
    "incomplete_answers_below": 27,
    "fast_duration_minutes": 12,
    "long_duration_minutes": 45,
    "background_mismatch_bands": 1,
    "attempt_spread_bands": 1,
}


#: Bank ``scoring_rules.thresholds`` key -> the constant it must equal. The
#: extractor reads these off the workbook, so this proves the numbers recorded
#: against a version are the workbook's own rather than a stale copy somebody
#: forgot to update when a package landed.
_WORKBOOK_CHECKS = {
    "band_minimum": REVIEW_POLICY["band_minimum"],
    "cumulative_threshold": REVIEW_POLICY["cumulative_threshold"],
    "incomplete_answers_below": REVIEW_POLICY["incomplete_answers_below"],
    "fast_duration_minutes": REVIEW_POLICY["fast_duration_minutes"],
    "long_duration_minutes": REVIEW_POLICY["long_duration_minutes"],
    "attempt_spread_bands": REVIEW_POLICY["attempt_spread_bands"],
}


def _same_threshold(found: float | int | None, expected: float | int) -> bool:
    """Equal, with a tolerance no real threshold change could hide behind.

    ``cumulative_threshold`` arrives as an IEEE double read out of a spreadsheet
    cell, so exact equality against the literal 0.7 is a coin flip on how the
    value was stored. Every threshold here is a policy number a human typed;
    the smallest meaningful change to any of them is far larger than 1e-9.
    """
    if found is None:
        return False
    return abs(float(found) - float(expected)) < 1e-9


def assert_policy_matches_workbook(bank: dict[str, Any]) -> None:
    """Refuse to import a bank whose workbook disagrees with our thresholds.

    Raises :class:`~app.services.placement_bank.PlacementBankError`, the same
    shape ``import_bank`` uses, so ``main`` reports it the same way and a test
    can assert on ``.code`` instead of matching a string out of ``SystemExit``.
    """
    rules = bank.get("scoring_rules")
    if not rules:
        # Banks extracted before v1.3 carry no rules block; nothing to check.
        return

    thresholds = rules.get("thresholds", {})
    drift = {
        name: (thresholds.get(name), expected)
        for name, expected in _WORKBOOK_CHECKS.items()
        if not _same_threshold(thresholds.get(name), expected)
    }
    if drift:
        raise placement_bank.PlacementBankError(
            "POLICY_DRIFT",
            "the workbook's thresholds differ from REVIEW_POLICY "
            f"{drift!r}. Reconcile placement_scoring.py and this script with "
            "the new workbook before importing.",
        )

    courses = {
        band: rules.get("course_map", {}).get(label)
        for band, label in (
            (0, "Below Band 1"), (1, "Legacy HSK1"), (2, "Legacy HSK2"),
            (3, "Legacy HSK3"), (4, "Legacy HSK4"), (5, "Legacy HSK5"),
            (6, "Legacy HSK6"),
        )
    }
    if courses != dict(placement_scoring.COURSE_BY_BAND):
        raise placement_bank.PlacementBankError(
            "COURSE_MAP_DRIFT",
            f"the workbook's course map {courses!r} differs from "
            f"COURSE_BY_BAND {dict(placement_scoring.COURSE_BY_BAND)!r}",
        )


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
    parser.add_argument(
        "--version-code",
        default=DEFAULT_VERSION,
        help=(
            "Names the bank FILE to read. The version recorded in the "
            "database is the `version_code` inside that file, which is not "
            "the same string."
        ),
    )
    parser.add_argument("--file", type=Path, default=None)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="report blocking issues without writing anything",
    )
    args = parser.parse_args(argv)

    bank = placement_bank.load_bank_file(args.file, version_code=args.version_code)
    try:
        assert_policy_matches_workbook(bank)
    except placement_bank.PlacementBankError as error:
        print(f"refusing to import: {error.code}: {error.message}")
        return 1

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
