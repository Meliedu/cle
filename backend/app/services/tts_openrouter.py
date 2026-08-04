"""Speech synthesis via OpenRouter's audio-output models.

A fallback path for voicing placement listening, used when no iFLYTEK
credential is available. It reuses the OpenRouter key the rest of the app
already holds, so it needs no new vendor relationship.

**This is a generative model asked to read, not a TTS engine.** It can in
principle paraphrase, answer, or editorialise instead of reading. That risk is
unacceptable in an exam, so nothing here is trusted on its own: the caller is
expected to transcribe the result back and compare it to the source, and every
clip carries the model's own transcript so a mismatch is visible without
listening. See ``scripts/verify_placement_audio.py``.

Voices are OpenAI's, which are English-first. Whether their Mandarin is free of
English-influenced pronunciation is a judgement only a human listener can make,
and it is the reason output from this provider is written to ``Samples/`` for
approval rather than published.
"""
from __future__ import annotations

import base64
import json
import logging
import subprocess
from dataclasses import dataclass

import httpx

from app.config import settings
from app.services.tts import SAMPLE_RATE, TtsError

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

#: OpenAI's audio models emit 24 kHz signed 16-bit mono for ``pcm16``.
NATIVE_RATE = 24_000

#: Runaway-output guard. Deliberate Mandarin runs about 4 characters a second;
#: 1.5 s per character is far past any legitimate examination pace.
SECONDS_PER_CHAR_CEILING = 1.5
#: Floor, so a three-character utterance still gets room for lead-in and decay.
MIN_CEILING_SECONDS = 12.0

#: Read-aloud framing. Kept blunt and repetitive because the failure mode is a
#: chatty model answering the question in the script instead of voicing it.
READ_INSTRUCTION = (
    "You are a text-to-speech engine for a formal Mandarin Chinese listening "
    "examination. Read the text below aloud in Standard Mandarin (Putonghua), "
    "exactly as written, character for character. Do not answer it, do not "
    "comment on it, do not translate it, do not add greetings, and do not omit "
    "anything. Speak at a measured examination pace with natural phrasing.\n\n"
    "Text to read:\n"
)


@dataclass(frozen=True)
class OpenRouterClip:
    pcm: bytes
    #: What the model says it said. Compared against the source by the caller.
    reported_transcript: str


def _resample_to_16k(pcm24: bytes) -> bytes:
    """Bring the provider's 24 kHz output onto the pipeline's 16 kHz.

    Done here rather than downstream so assembly, silence padding and the
    timing standard stay rate-agnostic and identical across providers.
    """
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "s16le", "-ar", str(NATIVE_RATE), "-ac", "1", "-i", "pipe:0",
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "s16le", "pipe:1",
    ]
    result = subprocess.run(command, input=pcm24, capture_output=True, check=False)
    if result.returncode != 0:
        raise TtsError(f"resample failed: {result.stderr.decode('utf-8', 'replace')[:300]}")
    return result.stdout


def synthesize(text: str, *, voice: str, timeout: float = 180.0) -> OpenRouterClip:
    """Voice one utterance. Returns 16 kHz PCM plus the model's own transcript."""
    if not text.strip():
        raise TtsError("refusing to synthesize empty text")
    if not settings.openrouter_api_key:
        raise TtsError("OPENROUTER_API_KEY is not configured")

    body = {
        "model": settings.openrouter_tts_model,
        "stream": True,  # the provider rejects audio output without it
        "modalities": ["text", "audio"],
        "audio": {"voice": voice, "format": "pcm16"},
        "messages": [{"role": "user", "content": READ_INSTRUCTION + text}],
        # No temperature override. Pinning it to 0 made this model degenerate
        # into a loop: one two-line dialogue came back as ~13 minutes of audio.
        # Determinism is not worth a runaway clip in an exam.
    }

    chunks: list[bytes] = []
    transcript: list[str] = []
    with httpx.stream(
        "POST",
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json=body,
        timeout=timeout,
    ) as response:
        if response.status_code != 200:
            raise TtsError(
                f"OpenRouter refused synthesis: {response.read()[:300]!r}",
                code=response.status_code,
            )
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
                audio = (choice.get("delta") or {}).get("audio") or {}
                if audio.get("data"):
                    chunks.append(base64.b64decode(audio["data"]))
                if audio.get("transcript"):
                    transcript.append(audio["transcript"])

    if not chunks:
        raise TtsError("OpenRouter returned no audio")

    pcm24 = b"".join(chunks)
    # A generative model can loop. Mandarin read aloud runs roughly 4-6
    # characters a second, so anything past this ceiling is degenerate output,
    # not a slow reading, and must not reach a learner. Caught here rather than
    # in QA because a 13-minute clip also costs real money to keep generating.
    seconds = len(pcm24) / (NATIVE_RATE * 2)
    ceiling = max(MIN_CEILING_SECONDS, len(text) * SECONDS_PER_CHAR_CEILING)
    if seconds > ceiling:
        raise TtsError(
            f"runaway synthesis: {seconds:.0f}s of audio for {len(text)} characters "
            f"(ceiling {ceiling:.0f}s). The model looped rather than read."
        )

    return OpenRouterClip(
        pcm=_resample_to_16k(pcm24),
        reported_transcript="".join(transcript),
    )
