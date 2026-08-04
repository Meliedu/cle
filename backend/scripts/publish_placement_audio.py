"""Publish approved listening audio: upload to R2, then populate the manifest.

The last step, deliberately separated from generation, because it is the only
one a learner can feel. Populating ``PlacementForm.audio_manifest`` flips
``audio_available`` true, which **removes the proctor instructions from the
sitting screen**. From that moment the recording is the only way to hear the
item, so a form must not be published until its audio is known good.

Two guards, both refusing rather than warning:

* ``--confirm-listened`` must be passed explicitly. There is no default and no
  prompt. Automated validation cannot judge tone accuracy, 一/不 and third-tone
  sandhi, polyphonic characters, neutral tone, 儿化音, or whether a voice
  carries English-influenced pronunciation, and those are the criteria this
  test is held to. A human states they listened, or nothing publishes.
* Every item in the form must have a clip. A partial manifest is worse than an
  empty one: the proctor notice disappears for all twelve listening items
  while only some can actually be heard.

    python scripts/publish_placement_audio.py --form A --stage Final --dry-run
    python scripts/publish_placement_audio.py --form A --stage Final --confirm-listened
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.placement import PlacementForm, PlacementItem, PlacementTestVersion  # noqa: E402
from app.services.placement_bank import BANK_DIR  # noqa: E402

EXPECTED_LISTENING_ITEMS = 12


def r2_key(version_code: str, form_code: str, question: int) -> str:
    return f"placement/{version_code}/{form_code}/q{question:02d}.mp3"


def collect_clips(stage_dir: Path, form_code: str) -> dict[int, Path]:
    clips: dict[int, Path] = {}
    for path in sorted(stage_dir.glob(f"Listening_Version{form_code}_Q*.mp3")):
        marker = path.stem.split("_Q")[1]
        number = marker.split("_")[0]
        if number.isdigit():
            clips[int(number)] = path
    return clips


async def publish(args: argparse.Namespace) -> int:
    stage_dir = Path(args.dir) if args.dir else (
        Path(args.out) / "Generated Listening Audio" / f"Version {args.form}" / args.stage
    )
    if not stage_dir.is_dir():
        print(f"no such folder: {stage_dir}", file=sys.stderr)
        return 2

    clips = collect_clips(stage_dir, args.form)
    missing = [q for q in range(1, EXPECTED_LISTENING_ITEMS + 1) if q not in clips]
    if missing:
        print(
            f"REFUSING: form {args.form} is missing clips for questions {missing}.\n"
            "A partial manifest removes the proctor notice from every listening "
            "item while only some can be heard.",
            file=sys.stderr,
        )
        return 1

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        version = (
            await db.execute(
                select(PlacementTestVersion)
                .where(PlacementTestVersion.status == "published")
                .order_by(PlacementTestVersion.published_at.desc())
            )
        ).scalars().first()
        if version is None:
            print("no published test version to attach audio to", file=sys.stderr)
            return 1

        form = (
            await db.execute(
                select(PlacementForm).where(
                    PlacementForm.test_version_id == version.id,
                    PlacementForm.form_code == args.form,
                )
            )
        ).scalar_one_or_none()
        if form is None:
            print(f"form {args.form} not found in {version.version_code}", file=sys.stderr)
            return 1

        # Version mismatch is the quietest catastrophic failure available here.
        # The clips were rendered from one bank's scripts; the rows they would
        # be attached to belong to whichever version is published. If those
        # differ, every learner hears a recording for a question they were not
        # asked, and the audio is plausible enough that nobody notices until
        # the scores make no sense. The QA log records what was generated, so
        # the two can be compared rather than assumed.
        qa_logs = sorted(stage_dir.glob("QA_Log_*.json"))
        if not qa_logs:
            print(
                f"REFUSING: no QA log in {stage_dir}. Without it there is no record "
                "of which test version these clips were generated from.",
                file=sys.stderr,
            )
            return 1
        generated_from = json.loads(qa_logs[0].read_text(encoding="utf-8")).get(
            "test_version_code"
        )
        if generated_from != version.version_code:
            print(
                f"REFUSING: version mismatch.\n"
                f"  clips generated from : {generated_from}\n"
                f"  currently published  : {version.version_code}\n"
                "Publishing these would play a recording of one paper's script "
                "over another paper's question.",
                file=sys.stderr,
            )
            return 1

        items = (
            await db.execute(
                select(PlacementItem).where(
                    PlacementItem.form_id == form.id,
                    PlacementItem.section == "listening",
                )
            )
        ).scalars().all()
        questions = {item.question_number for item in items}
        uncovered = sorted(questions - set(clips))
        if uncovered:
            print(f"REFUSING: no clip for delivered questions {uncovered}", file=sys.stderr)
            return 1

        manifest: dict[str, dict] = {}
        for question in sorted(questions):
            path = clips[question]
            data = path.read_bytes()
            key = r2_key(version.version_code, args.form, question)
            manifest[str(question)] = {
                "r2_key": key,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "source_file": path.name,
            }
            if args.dry_run:
                print(f"  would upload {path.name} -> {key} ({len(data):,}B)")
                continue
            from app.services.storage import upload_file

            upload_file(key, data, "audio/mpeg")
            print(f"  uploaded {path.name} -> {key} ({len(data):,}B)")

        if args.dry_run:
            print(
                f"\nDRY RUN. Would publish {len(manifest)} clips for form {args.form} "
                f"of {version.version_code}.\nThis would remove the proctor notice "
                f"for form {args.form}."
            )
            return 0

        form.audio_manifest = manifest
        await db.commit()
        print(
            f"\nPUBLISHED {len(manifest)} clips for form {args.form} of "
            f"{version.version_code}.\nLearners on this form now hear recordings; "
            f"the proctor notice is gone."
        )
    await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--form", required=True)
    parser.add_argument("--stage", default="Final", choices=["Samples", "Draft", "Final"])
    parser.add_argument("--out", default="tmp/placement-audio")
    parser.add_argument("--dir", help="explicit stage folder, overriding --out/--stage")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--confirm-listened",
        action="store_true",
        help=(
            "state that a human has listened to this form end to end and judged "
            "the pronunciation acceptable for a formal examination"
        ),
    )
    args = parser.parse_args()

    if not args.dry_run and not args.confirm_listened:
        print(
            "REFUSING: --confirm-listened not given.\n\n"
            "Publishing removes the proctor instructions from the sitting screen, "
            "after which the recording is the only way to hear an item. No "
            "automated check can judge tone accuracy, 一/不 or third-tone sandhi, "
            "polyphonic characters, neutral tone, 儿化音, or English-influenced "
            "pronunciation.\n\n"
            "Listen to the form end to end, then re-run with --confirm-listened.",
            file=sys.stderr,
        )
        return 2

    return asyncio.run(publish(args))


if __name__ == "__main__":
    raise SystemExit(main())
