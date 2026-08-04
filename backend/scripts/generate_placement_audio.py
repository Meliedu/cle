"""Voice the placement listening scripts, one exam version at a time.

Two products, because two different consumers need different things:

* **per-item clips**, which the app delivers. One item is one file, holding ONE
  reading. The paper's "read twice" survives as ``audio_playback``, spent as
  replays the learner triggers, so the second listening happens when they want
  it rather than when a tape reaches it.
* **a section tape** per form, which is what CLE reviews and archives. Items
  are concatenated with the documented pauses and each script is heard twice,
  the way a room sitting would run.

Forms never mix. Every path, manifest and QA log is scoped by form code, and
the script refuses to write a form's output into another form's folder.

Nothing here rewrites a transcript. The text handed to the synthesizer is the
text in the bank, which ``verify_placement_audio`` re-checks against the
Administrator Pack. Source defects are reported, never repaired in passing.

    python scripts/generate_placement_audio.py --dry-run
    python scripts/generate_placement_audio.py --form A --stage Draft
    python scripts/generate_placement_audio.py --stage Final --upload
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services import tts  # noqa: E402
from app.services.placement_audio import (  # noqa: E402
    BEFORE_REPEAT_MS,
    BETWEEN_QUESTIONS_MS,
    BETWEEN_REPEATS_MS,
    END_OF_SECTION_MS,
    Turn,
    _silence,
    assemble_pcm,
    encode_mp3,
    pcm_duration_seconds,
    segment_transcript,
)
from app.services.placement_bank import BANK_DIR, load_bank_file  # noqa: E402

DEFAULT_BANK = BANK_DIR / "meli-placement-v1.3.json"
LISTENING_SECTION = "listening"
#: The listening block is questions 1-12, i.e. Section 1 of the paper.
SECTION_LABEL = "Section1"


def version_folder(root: Path, form_code: str) -> Path:
    return root / "Generated Listening Audio" / f"Version {form_code}"


def item_filename(form_code: str, question: int, stage: str) -> str:
    return f"Listening_Version{form_code}_Q{question:02d}_{stage}.mp3"


def section_filename(form_code: str, stage: str) -> str:
    return f"Listening_Version{form_code}_{SECTION_LABEL}_{stage}.mp3"


def complete_filename(form_code: str) -> str:
    return f"Listening_Version{form_code}_Complete_Final.mp3"


def r2_key(version_code: str, form_code: str, question: int) -> str:
    return f"placement/{version_code}/{form_code}/q{question:02d}.mp3"


@dataclass
class ItemResult:
    form_code: str
    question: int
    turns: tuple[Turn, ...]
    transcript: str
    mp3: bytes = b""
    pcm: bytes = b""
    duration_s: float = 0.0
    sha256: str = ""
    issues: list[str] = field(default_factory=list)


def voice_for(role: str) -> str:
    return settings.iflytek_tts_voice_male if role == "male" else settings.iflytek_tts_voice_female


async def synthesize_item(form_code: str, item: dict[str, Any], *, dry_run: bool) -> ItemResult:
    transcript = item["restricted"]["transcript"]
    turns = segment_transcript(transcript)
    result = ItemResult(
        form_code=form_code,
        question=item["question_number"],
        turns=turns,
        transcript=transcript,
    )
    if dry_run:
        return result

    clips: list[bytes] = []
    for turn in turns:
        clips.append(await tts.synthesize_with_retry(turn.text, voice=voice_for(turn.voice)))
    result.pcm = assemble_pcm(clips)
    result.duration_s = pcm_duration_seconds(result.pcm)
    result.mp3 = encode_mp3(result.pcm)
    result.sha256 = hashlib.sha256(result.mp3).hexdigest()
    return result


def build_section_tape(results: list[ItemResult], playbacks: dict[int, int]) -> bytes:
    """Concatenate a form's items into the tape a room sitting would hear."""
    parts: list[bytes] = []
    for index, result in enumerate(sorted(results, key=lambda r: r.question)):
        if index:
            parts.append(_silence(BETWEEN_QUESTIONS_MS))
        plays = playbacks.get(result.question, 1)
        for play in range(plays):
            if play:
                parts.append(_silence(BETWEEN_REPEATS_MS))
            elif plays > 1:
                pass
            parts.append(result.pcm)
        if plays > 1:
            parts.append(_silence(BEFORE_REPEAT_MS))
    parts.append(_silence(END_OF_SECTION_MS))
    return encode_mp3(b"".join(parts))


async def run(args: argparse.Namespace) -> int:
    bank = load_bank_file(Path(args.bank))
    version_code = bank["version_code"]
    root = Path(args.out).resolve()
    stage = args.stage

    forms = [f for f in bank["forms"] if not args.form or f["form_code"] in args.form]
    if not forms:
        print(f"no forms matched {args.form!r}", file=sys.stderr)
        return 2

    generated_at = datetime.now(timezone.utc).isoformat()
    overall_ok = True

    for form in sorted(forms, key=lambda f: f["form_code"]):
        code = form["form_code"]
        items = [i for i in form["items"] if i["section"] == LISTENING_SECTION]
        items.sort(key=lambda i: i["question_number"])
        playbacks = {i["question_number"]: (i.get("audio_playback") or 1) for i in items}

        out_dir = version_folder(root, code) / stage
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n=== Version {code}: {len(items)} listening items -> {out_dir} ===")
        results: list[ItemResult] = []
        manifest: dict[str, Any] = {}

        for item in items:
            res = await synthesize_item(code, item, dry_run=args.dry_run)
            results.append(res)
            speakers = "/".join(f"{t.speaker or 'narrator'}:{t.voice}" for t in res.turns)
            if args.dry_run:
                print(f"  Q{res.question:02d} [{len(res.turns)} turn(s)] {speakers}")
                continue

            path = out_dir / item_filename(code, res.question, stage)
            path.write_bytes(res.mp3)
            manifest[str(res.question)] = {
                "r2_key": r2_key(version_code, code, res.question),
                "duration_ms": round(res.duration_s * 1000),
                "sha256": res.sha256,
                "turns": len(res.turns),
                "playback": playbacks[res.question],
            }
            print(f"  Q{res.question:02d} {res.duration_s:6.2f}s  {len(res.mp3):>7,}B  {speakers}")

        if args.dry_run:
            continue

        tape = build_section_tape(results, playbacks)
        (out_dir / section_filename(code, stage)).write_bytes(tape)
        if stage == "Final":
            (out_dir / complete_filename(code)).write_bytes(tape)

        qa_log = {
            "exam_version": f"Version {code}",
            "test_version_code": version_code,
            "transcript_source": bank.get("source_package"),
            "transcript_source_file": "Meli_Placement_Test_v1.3_Administrator_Pack.pdf",
            "tts_provider": "iFLYTEK online TTS (WebSocket v2)",
            "tts_endpoint": f"wss://{tts.TTS_HOST}{tts.TTS_PATH}",
            "voice_configuration": {
                "male": settings.iflytek_tts_voice_male,
                "female": settings.iflytek_tts_voice_female,
                "speed": settings.iflytek_tts_speed,
                "sample_rate_hz": tts.SAMPLE_RATE,
                "encoding": "MP3 64kbps mono, loudnorm I=-16 TP=-1.5 LRA=11",
            },
            "timing_standard_ms": {
                "lead_in": 350, "turn_gap": 450, "tail": 250,
                "between_questions": BETWEEN_QUESTIONS_MS,
                "before_repeat": BEFORE_REPEAT_MS,
                "between_repeats": BETWEEN_REPEATS_MS,
                "end_of_section": END_OF_SECTION_MS,
            },
            "generated_at": generated_at,
            "stage": stage,
            "items": manifest,
            "issues_found": [i for r in results for i in r.issues],
            "corrections_made": [],
            "final_qa_status": "PENDING_HUMAN_LISTEN",
        }
        (out_dir / f"QA_Log_Version{code}_{stage}.json").write_text(
            json.dumps(qa_log, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (version_folder(root, code) / f"audio_manifest_{code}.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if args.upload:
            from app.services.storage import upload_file

            for res in results:
                upload_file(
                    r2_key(version_code, code, res.question), res.mp3, "audio/mpeg"
                )
            print(f"  uploaded {len(results)} clips to R2")

    print("\ndry run complete" if args.dry_run else "\ngeneration complete")
    return 0 if overall_ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bank", default=str(DEFAULT_BANK))
    p.add_argument("--out", default="tmp/placement-audio")
    p.add_argument("--form", action="append", help="limit to a form code; repeatable")
    p.add_argument("--stage", default="Draft", choices=["Samples", "Draft", "Final"])
    p.add_argument("--dry-run", action="store_true", help="segment and report, call no vendor")
    p.add_argument("--upload", action="store_true", help="also upload clips to R2")
    return asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
