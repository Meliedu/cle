"""Check that generated listening audio actually says the script.

The automated half of QA. It cannot judge whether a reading sounds like a
native examiner, and nothing here pretends to: tone accuracy, sandhi, 儿化音 and
English-influenced pronunciation are all human judgements. What it can do is
catch the failures a human listener is worst at spotting reliably across 60
clips: a missing sentence, a swapped character, a paraphrase, or a clip that
belongs to a different item entirely.

Two independent checks per clip:

1. **Reported transcript** -- what the synthesizer says it said. Free, but it
   is the model marking its own homework, so it is necessary and not sufficient.
2. **Round-trip ASR** -- transcribe the rendered audio with Whisper and compare
   that to the source. This is the one that catches a model which reported the
   right text and voiced something else.

Comparison ignores punctuation and whitespace, because a synthesizer is not
expected to voice a full stop, and normalises to Simplified via the characters
actually present. Anything else is a difference worth a human's attention.

    python scripts/verify_placement_audio.py --dir "tmp/placement-audio/..." --bank ...
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.placement_bank import BANK_DIR, load_bank_file  # noqa: E402
from app.services.placement_audio import segment_transcript  # noqa: E402

DEFAULT_BANK = BANK_DIR / "meli-placement-v1.3.json"

#: Everything a reader would not voice: punctuation, spacing, and the speaker
#: labels, which are stage direction printed for a proctor.
_STRIP = re.compile(r"[\s，。！？、；：“”‘’（）()\[\]—…·,.!?;:\"']+")


def spoken_form(text: str) -> str:
    """The characters a reader would actually utter, in order."""
    normalised = unicodedata.normalize("NFKC", text)
    return _STRIP.sub("", normalised)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def compare(source: str, heard: str) -> dict:
    src, got = spoken_form(source), spoken_form(heard)
    ratio = similarity(src, got)
    missing = [c for c in src if c not in got]
    return {
        "match": src == got,
        "similarity": round(ratio, 4),
        "source_chars": len(src),
        "heard_chars": len(got),
        "sample_missing": "".join(missing[:20]),
    }


def transcribe(path: Path) -> str:
    """Round-trip the rendered clip back to text.

    This is the check that matters. The synthesizer's own reported transcript
    is the model marking its own homework; this reads the waveform that will
    actually reach a learner, so it catches a clip that reported the right
    text and voiced something else, or nothing.

    Uses OpenRouter's audio-input models rather than local Whisper: the repo's
    Whisper path needs an ``OPENAI_API_KEY`` that this project deliberately
    does not set (everything goes through OpenRouter).
    """
    import base64
    import subprocess

    import httpx

    from app.config import settings

    wav = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
        capture_output=True, check=True,
    ).stdout

    body = {
        "model": settings.openrouter_asr_model,
        "stream": True,
        "modalities": ["text"],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": (
                "Transcribe this Mandarin audio verbatim in Simplified Chinese "
                "characters. Output only the transcription, nothing else."
            )},
            {"type": "input_audio",
             "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"}},
        ]}],
    }

    parts: list[str] = []
    with httpx.stream(
        "POST", "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json=body, timeout=300,
    ) as response:
        if response.status_code != 200:
            raise SystemExit(f"ASR failed: {response.read()[:300]!r}")
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload.strip() == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            for choice in event.get("choices") or []:
                delta = (choice.get("delta") or {}).get("content")
                if delta:
                    parts.append(delta)
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="a stage folder holding the clips")
    parser.add_argument("--bank", default=str(DEFAULT_BANK))
    parser.add_argument("--form", required=True)
    parser.add_argument("--no-asr", action="store_true", help="skip the Whisper round trip")
    args = parser.parse_args()

    bank = load_bank_file(Path(args.bank))
    form = next(f for f in bank["forms"] if f["form_code"] == args.form)
    scripts = {
        item["question_number"]: item["restricted"]["transcript"]
        for item in form["items"]
        if item["section"] == "listening"
    }

    stage_dir = Path(args.dir)
    reported = {}
    reported_path = stage_dir / "reported_transcripts.json"
    if reported_path.exists():
        reported = json.loads(reported_path.read_text(encoding="utf-8"))

    findings: list[dict] = []
    for question, script in sorted(scripts.items()):
        clip = next(iter(stage_dir.glob(f"*Q{question:02d}_*.mp3")), None)
        entry: dict = {"question": question, "clip": clip.name if clip else None}

        # The script as it will be *spoken*: labels removed, turns joined.
        spoken_source = "".join(turn.text for turn in segment_transcript(script))

        if question_reported := reported.get(str(question)):
            entry["reported"] = compare(spoken_source, question_reported)
        if clip is None:
            entry["error"] = "no clip found"
        elif not args.no_asr:
            entry["asr"] = compare(spoken_source, transcribe(clip))
        findings.append(entry)

    failures = [
        f
        for f in findings
        if f.get("error")
        or (f.get("asr") and f["asr"]["similarity"] < 0.90)
        or (f.get("reported") and not f["reported"]["match"])
    ]

    out = stage_dir / f"verification_Version{args.form}.json"
    out.write_text(
        json.dumps({"findings": findings, "failures": len(failures)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for finding in findings:
        asr = finding.get("asr") or {}
        rep = finding.get("reported") or {}
        flag = "FAIL" if finding in failures else "ok  "
        print(
            f"  {flag} Q{finding['question']:02d} "
            f"reported={'=' if rep.get('match') else rep.get('similarity', '-')} "
            f"asr={asr.get('similarity', '-')}"
            + (f"  {finding['error']}" if finding.get("error") else "")
        )
    print(f"\n{len(failures)} of {len(findings)} clips need a human look. Report: {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
