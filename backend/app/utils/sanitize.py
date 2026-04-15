"""Shared sanitization helpers for user-provided text that flows into LLM prompts."""

from __future__ import annotations

import re

_MAX_QUERY_CHARS = 2000
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_query(text: str | None) -> str:
    """Strip control characters and bound length before feeding user text to
    the LLM. Defence in depth against prompt injection payloads delivered via
    free-text fields (``query``/``title``) that get interpolated into prompts."""
    cleaned = _CONTROL_CHARS_RE.sub(" ", text or "")
    cleaned = cleaned.strip()
    if len(cleaned) > _MAX_QUERY_CHARS:
        cleaned = cleaned[:_MAX_QUERY_CHARS]
    return cleaned
