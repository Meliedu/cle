"""Vision LLM client — captions for figures in PDFs/PPTX via OpenRouter.

caption_image never raises into the pipeline: a timeout, rate limit, or
upstream error returns None so the parser can drop the caption and keep
text-only content flowing.
"""

from __future__ import annotations

import asyncio
import base64
import logging

import httpx
import openai
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

_CAPTION_PROMPT = (
    "You are describing a figure from a university lecture slide or textbook "
    "page for a student who can't see it. Be concrete and information-dense. "
    "Prefer labels, axes, data points, relationships, and what the figure is "
    "*about* over generic descriptions. Keep it under 80 words. Output only "
    "the description — no preamble, no 'This figure shows...'."
)

_MAX_CAPTION_TOKENS = 250
_MAX_ATTEMPTS = 3


def _detect_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image_bytes.startswith(b"GIF8"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _get_client() -> AsyncOpenAI:
    global _client  # noqa: PLW0603
    if _client is None:
        timeout = httpx.Timeout(
            connect=10.0,
            read=float(settings.vlm_timeout_seconds),
            write=30.0,
            pool=10.0,
        )
        _client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=timeout,
            max_retries=0,
        )
    return _client


async def caption_image(image_bytes: bytes, context: str = "") -> str | None:
    """Return a short caption for the image, or None on any failure.

    context is optional surrounding text (slide text, nearby paragraph) that
    helps the VLM disambiguate figures. Trimmed to keep the prompt tight.
    """
    if not image_bytes:
        return None
    if not settings.enable_figure_captions:
        return None
    if not settings.openrouter_api_key:
        logger.warning("caption_image skipped: OPENROUTER_API_KEY not set")
        return None

    mime = _detect_mime(image_bytes)
    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    prompt = _CAPTION_PROMPT
    if context:
        trimmed = context.strip().replace("\n", " ")[:800]
        if trimmed:
            prompt = f"{_CAPTION_PROMPT}\n\nSurrounding text for context:\n{trimmed}"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }
    ]

    client = _get_client()
    delay = 1.0
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await client.chat.completions.create(
                model=settings.vlm_model,
                messages=messages,
                max_tokens=_MAX_CAPTION_TOKENS,
            )
            caption = (response.choices[0].message.content or "").strip()
            return caption or None
        except (
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ) as exc:
            if attempt == _MAX_ATTEMPTS:
                logger.warning("VLM caption failed after retries: %s", exc)
                return None
            await asyncio.sleep(delay)
            delay *= 2
        except Exception as exc:  # noqa: BLE001 — never escape
            logger.warning(
                "VLM caption failed (non-retryable): %s (mime=%s, bytes=%d)",
                exc,
                mime,
                len(image_bytes),
            )
            return None
    return None
