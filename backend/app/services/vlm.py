"""Vision LLM client — captions for figures in PDFs/PPTX via OpenRouter.

caption_image never raises into the pipeline: a timeout, rate limit, or
upstream error returns None so the parser can drop the caption and keep
text-only content flowing.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re as _re

import httpx
import openai
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

_CAPTION_MAX_CHARS = 1800
_PAGE_MAX_CHARS = 8000
_CAPTION_INJECTION_PATTERNS = _re.compile(
    r"(ignore\s+(all|previous|prior)|system\s+prompt|<\|\w+\|>|\[INST\]|\[/INST\])",
    _re.IGNORECASE,
)


def _sanitize_vlm_text(raw: str, *, max_chars: int, fallback: str) -> str:
    """Post-process raw VLM output before it enters the chunk pipeline.

    Protects against indirect prompt-injection carried in adversarial image
    text: the VLM faithfully transcribes "Ignore all previous instructions"
    written inside a slide, and we don't want that payload to flow into
    downstream LLM prompts verbatim.
    """
    cleaned = (raw or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "…"
    if _CAPTION_INJECTION_PATTERNS.search(cleaned):
        return fallback
    return cleaned


# Caption prompt: describe visuals AND transcribe any readable text. Slide
# decks, screenshots, and scanned textbook pages often surface here as
# "figures"; verbatim text preserves content that would otherwise be reduced
# to a vague summary.
_CAPTION_PROMPT = (
    "You are extracting content from a university lecture slide, textbook "
    "page, or figure for a student. If the image contains substantial "
    "readable text (slide bullets, screenshot, scanned page), transcribe "
    "ALL visible text VERBATIM first, preserving order and line breaks. "
    "Then, only if there is additional visual content (diagram, chart, "
    "photograph), briefly describe it — labels, axes, data points, "
    "relationships. Omit the description when the image is pure text. "
    "Keep total output under 300 words. Output only the content — no "
    "preamble, no 'This figure shows…'."
)

# Page-transcription prompt: full-page OCR rescue for scanned/image-only
# PDF pages. Longer output budget than figure captions.
_PAGE_PROMPT = (
    "This is a page from a university lecture, textbook, or slide deck. "
    "Transcribe ALL readable text VERBATIM, preserving reading order and "
    "line breaks. Keep headings, bullets, numbered lists, and equations "
    "intact. If there are diagrams, charts, or photos, add a short "
    "bracketed description like [Figure: bar chart comparing X and Y] "
    "placed where it appears in the reading flow. Output only the page "
    "content — no preamble."
)

_MAX_CAPTION_TOKENS = 600
_MAX_PAGE_TOKENS = 2500
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


async def _vlm_call(
    prompt: str,
    image_bytes: bytes,
    *,
    max_tokens: int,
    log_label: str,
) -> str | None:
    """Send a single prompt+image to the VLM with retries. Never raises."""
    if not image_bytes:
        return None
    if not settings.enable_figure_captions:
        return None
    if not settings.openrouter_api_key:
        logger.warning("%s skipped: OPENROUTER_API_KEY not set", log_label)
        return None

    mime = _detect_mime(image_bytes)
    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"

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
                max_tokens=max_tokens,
            )
            return (response.choices[0].message.content or "").strip() or None
        except (
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ) as exc:
            if attempt == _MAX_ATTEMPTS:
                logger.warning("%s failed after retries: %s", log_label, exc)
                return None
            await asyncio.sleep(delay)
            delay *= 2
        except Exception as exc:  # noqa: BLE001 — never escape
            logger.warning(
                "%s failed (non-retryable): %s (mime=%s, bytes=%d)",
                log_label,
                exc,
                mime,
                len(image_bytes),
            )
            return None
    return None


async def caption_image(image_bytes: bytes, context: str = "") -> str | None:
    """Return a caption for the image, or None on any failure.

    context is optional surrounding text (slide text, nearby paragraph) that
    helps the VLM disambiguate figures. Trimmed to keep the prompt tight.
    """
    prompt = _CAPTION_PROMPT
    if context:
        trimmed = context.strip().replace("\n", " ")[:800]
        if trimmed:
            prompt = f"{_CAPTION_PROMPT}\n\nSurrounding text for context:\n{trimmed}"

    raw = await _vlm_call(
        prompt,
        image_bytes,
        max_tokens=_MAX_CAPTION_TOKENS,
        log_label="VLM caption",
    )
    if raw is None:
        return None
    return _sanitize_vlm_text(
        raw,
        max_chars=_CAPTION_MAX_CHARS,
        fallback="[Figure: (caption omitted — flagged pattern)]",
    ) or None


async def transcribe_page(image_bytes: bytes) -> str | None:
    """Verbatim-transcribe a full PDF page rendered to an image.

    Used as a rescue pass when the primary text extractor (docling/pymupdf)
    returns very little for a page — typically a scanned page or a slide
    exported to PDF as raster. Never raises.
    """
    raw = await _vlm_call(
        _PAGE_PROMPT,
        image_bytes,
        max_tokens=_MAX_PAGE_TOKENS,
        log_label="VLM page transcription",
    )
    if raw is None:
        return None
    return _sanitize_vlm_text(
        raw,
        max_chars=_PAGE_MAX_CHARS,
        fallback="",  # drop the page entirely if injection detected
    ) or None
