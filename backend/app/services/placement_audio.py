"""Turn a listening script into one delivered clip.

A placement listening script is not a block of prose. 46 of the 60 are
two-speaker 男/女 dialogues, 5 are interviews with role labels (记者/专家,
主持人/研究者), and 9 are single-voice monologues. The speaker label is stage
direction printed for the proctor: it tells them who to voice, and it is never
spoken. Handing the raw transcript to a synthesizer would read the labels
aloud in one voice and destroy the turn-taking the items actually test.

One clip contains ONE reading. The paper's "read twice" instruction survives as
``PlacementItem.audio_playback``, which the delivery layer spends as replays,
so a learner who needs the second listening chooses when to take it.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Literal, Sequence

from app.services.tts import CHANNELS, SAMPLE_RATE, SAMPLE_WIDTH

logger = logging.getLogger(__name__)

VoiceRole = Literal["male", "female"]

#: Full-width and half-width colon both occur in the source package.
_LABEL_RE = re.compile(r"^([^：:]{1,6})[：:]\s*(.+)$", re.DOTALL)

#: A sentence the extractor finished; anything else at a line end is a wrap.
_TERMINAL = "。？！?!”\"…"

#: Labels whose voice is stated by the label itself.
_GENDERED: dict[str, VoiceRole] = {"男": "male", "女": "female"}

# --------------------------------------------------------------------------
# Timing standard.
#
# The v1.3 package specifies repetition ("Read/play each script twice") but no
# durations, so these are established here and applied identically to every
# form. They are constants rather than parameters on purpose: a pause that
# differed between Form A and Form B would make the forms measurably unequal
# in a way no score adjustment could undo.
# --------------------------------------------------------------------------

#: Silence between speaker turns. Long enough to hear the handover, short
#: enough that a 5-turn dialogue does not outrun the item's expected_seconds.
TURN_GAP_MS = 450
#: Lead-in, so the first syllable is not clipped by a player starting late.
LEAD_IN_MS = 350
TAIL_MS = 250

#: Section-tape timings, used when items are concatenated into one file for
#: CLE review and archive. Per-item delivery in the app does not use these:
#: there the learner controls when the next item and the replay begin.
AFTER_SECTION_INSTRUCTION_MS = 1_500
BETWEEN_QUESTIONS_MS = 2_000
BEFORE_REPEAT_MS = 1_500
BETWEEN_REPEATS_MS = 1_500
END_OF_SECTION_MS = 2_000


@dataclass(frozen=True)
class Turn:
    """One utterance by one speaker."""

    speaker: str | None  # the printed label, or None for an unlabelled monologue
    text: str  # what is spoken; never includes the label
    voice: VoiceRole


def _join_wrapped_lines(lines: Sequence[str]) -> list[str]:
    """Re-join a sentence the source PDF split across two printed lines.

    ``scripts/pdf_layout.py`` rebuilds paragraphs from geometry and treats a
    line reaching the right margin as a wrap, but one script in v1.3 slipped
    through: form C Q12 breaks 效果 across lines, leaving ``果负责：`` at the
    start of the next line. That reads as a speaker label, so a naive parser
    switches voice mid-sentence and swallows the two characters that carry the
    meaning. The rule that catches it is the one the extractor already uses in
    reverse: a line that does not end a sentence has not ended.
    """
    joined: list[str] = []
    for line in lines:
        if joined and joined[-1] and joined[-1][-1] not in _TERMINAL:
            joined[-1] = joined[-1] + line
        else:
            joined.append(line)
    return joined


def segment_transcript(transcript: str) -> tuple[Turn, ...]:
    """Split a script into voiced turns.

    Unlabelled scripts become a single narrator turn rather than an error: a
    monologue is a legitimate item type here, not a malformed dialogue.
    """
    lines = [ln.strip() for ln in transcript.strip().split("\n") if ln.strip()]
    if not lines:
        raise ValueError("empty transcript")

    lines = _join_wrapped_lines(lines)
    matches = [_LABEL_RE.match(ln) for ln in lines]

    if not all(matches):
        # Mixed labelled/unlabelled would mean the wrap-join above missed
        # something; refuse rather than voice half a script as narration.
        if any(matches):
            raise ValueError(
                "transcript mixes labelled and unlabelled lines after wrap-joining: "
                f"{lines!r}"
            )
        return (Turn(speaker=None, text=" ".join(lines), voice="female"),)

    labels = [m.group(1) for m in matches]  # type: ignore[union-attr]

    # Ungendered role labels (记者/专家) get a stable voice by order of first
    # appearance, so regenerating the bank never reshuffles who sounds like whom.
    assigned: dict[str, VoiceRole] = {}
    for label in labels:
        if label in assigned:
            continue
        if label in _GENDERED:
            assigned[label] = _GENDERED[label]
        else:
            assigned[label] = "female" if len(assigned) % 2 == 0 else "male"

    return tuple(
        Turn(speaker=label, text=m.group(2).strip(), voice=assigned[label])  # type: ignore[union-attr]
        for label, m in zip(labels, matches)
    )


def _silence(ms: int) -> bytes:
    return b"\x00" * int(SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS * ms / 1000)


def assemble_pcm(clips: Sequence[bytes]) -> bytes:
    """Concatenate synthesized turns into one PCM stream with natural gaps."""
    if not clips:
        raise ValueError("no clips to assemble")
    out = [_silence(LEAD_IN_MS)]
    for index, clip in enumerate(clips):
        if index:
            out.append(_silence(TURN_GAP_MS))
        out.append(clip)
    out.append(_silence(TAIL_MS))
    return b"".join(out)


def encode_mp3(pcm: bytes) -> bytes:
    """Encode PCM to MP3, normalized to a consistent loudness.

    Loudness normalization is not polish. Turns come back from the vendor at
    whatever level it chose, and an exam where one item is audibly quieter than
    the next makes the learner's volume knob part of the measurement.
    """
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "64k",
        "-f", "mp3", "pipe:1",
    ]
    result = subprocess.run(command, input=pcm, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode('utf-8', 'replace')[:400]}")
    if not result.stdout:
        raise RuntimeError("ffmpeg produced no output")
    return result.stdout


def pcm_duration_seconds(pcm: bytes) -> float:
    return len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS)
