"""iFLYTEK online speech synthesis (streaming WebSocket v2).

Synthesis only, and deliberately separate from :mod:`app.services.speech`.
The two share a vendor account and its credential triple, and nothing else:
``speech.py`` grades audio a learner produced, this produces audio a learner
will hear. Folding them together would put exam-delivery content on the same
code path as transient learner recordings, which have opposite retention rules.

Returns raw PCM rather than MP3 on purpose. Callers stitch several turns of a
dialogue into one clip, and concatenating encoded MP3 frames from separate
requests is not reliably gapless; concatenating PCM is exact. Encoding happens
once, at the end, in :mod:`app.services.placement_audio`.

API: https://www.xfyun.cn/doc/tts/online_tts/API.html
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from email.utils import format_datetime
from datetime import datetime, timezone
from urllib.parse import urlencode

import websockets

from app.config import settings

logger = logging.getLogger(__name__)

TTS_HOST = "tts-api.xfyun.cn"
TTS_PATH = "/v2/tts"

#: The vendor returns signed 16-bit little-endian mono at this rate when asked
#: for ``aue=raw`` with ``auf=audio/L16;rate=16000``.
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
CHANNELS = 1

#: The vendor caps a single call at 8000 bytes (~2000 Han characters). Every
#: placement script is far below this (longest is 198 characters), so a script
#: that trips this is a data fault worth failing on rather than silently
#: truncating a sentence a learner is about to be tested on.
MAX_TEXT_BYTES = 8_000


class TtsError(RuntimeError):
    """A synthesis request the vendor refused, or a response we cannot use."""

    def __init__(self, message: str, *, code: int | None = None, sid: str | None = None):
        super().__init__(message)
        self.code = code
        self.sid = sid


def _signed_url(api_key: str, api_secret: str) -> str:
    """Build the authenticated wss URL.

    The signature covers the literal request line, so ``TTS_PATH`` must match
    what the handshake actually sends. The vendor tolerates 300s of clock skew
    and rejects anything further, which is the usual cause of a 401 here.
    """
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    signature_origin = f"host: {TTS_HOST}\ndate: {date}\nGET {TTS_PATH} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(
            api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
    query = urlencode({"authorization": authorization, "date": date, "host": TTS_HOST})
    return f"wss://{TTS_HOST}{TTS_PATH}?{query}"


def _request_payload(text: str, *, voice: str, speed: int, volume: int, pitch: int) -> str:
    return json.dumps(
        {
            "common": {"app_id": settings.iflytek_app_id},
            "business": {
                "aue": "raw",
                "auf": f"audio/L16;rate={SAMPLE_RATE}",
                "vcn": voice,
                "tte": "UTF8",
                "speed": speed,
                "volume": volume,
                "pitch": pitch,
            },
            "data": {
                "status": 2,
                "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
            },
        }
    )


async def synthesize(
    text: str,
    *,
    voice: str,
    speed: int | None = None,
    volume: int = 50,
    pitch: int = 50,
    timeout: float = 30.0,
) -> bytes:
    """Synthesize one utterance to raw PCM.

    One utterance, not one script: a two-speaker dialogue is several calls,
    because ``vcn`` is fixed for the length of a request.
    """
    if not text.strip():
        raise TtsError("refusing to synthesize empty text")
    encoded_len = len(text.encode("utf-8"))
    if encoded_len > MAX_TEXT_BYTES:
        raise TtsError(f"text is {encoded_len} bytes, vendor limit is {MAX_TEXT_BYTES}")
    if not (settings.iflytek_app_id and settings.iflytek_api_key and settings.iflytek_api_secret):
        raise TtsError("iFLYTEK credentials are not configured")

    if speed is None:
        speed = settings.iflytek_tts_speed

    url = _signed_url(settings.iflytek_api_key, settings.iflytek_api_secret)
    chunks: list[bytes] = []

    async with websockets.connect(url, open_timeout=timeout, close_timeout=5) as ws:
        await ws.send(_request_payload(text, voice=voice, speed=speed, volume=volume, pitch=pitch))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            frame = json.loads(raw)
            code = frame.get("code")
            if code != 0:
                raise TtsError(
                    f"iFLYTEK refused synthesis: {frame.get('message')}",
                    code=code,
                    sid=frame.get("sid"),
                )
            data = frame.get("data") or {}
            if data.get("audio"):
                chunks.append(base64.b64decode(data["audio"]))
            # status 2 is the vendor's end-of-stream marker.
            if data.get("status") == 2:
                break

    audio = b"".join(chunks)
    if not audio:
        raise TtsError("iFLYTEK returned no audio")
    return audio


async def synthesize_with_retry(
    text: str, *, voice: str, attempts: int = 3, **kwargs
) -> bytes:
    """Retry transient failures.

    A dropped socket mid-clip is common enough on this vendor that a one-shot
    generator would fail a 60-item batch most runs. Vendor *refusals* (a code
    in the frame, e.g. an unactivated voice) are not retried: they will refuse
    identically three times and the error is worth surfacing immediately.
    """
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await synthesize(text, voice=voice, **kwargs)
        except TtsError as exc:
            if exc.code is not None:
                raise
            last = exc
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
            last = exc
        if attempt < attempts:
            backoff = 2 ** (attempt - 1)
            logger.warning(
                "TTS attempt %d/%d failed (%s); retrying in %ds", attempt, attempts, last, backoff
            )
            await asyncio.sleep(backoff)
    raise TtsError(f"synthesis failed after {attempts} attempts: {last}")
