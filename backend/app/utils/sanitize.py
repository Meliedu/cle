"""Shared sanitization helpers for user-provided text that flows into LLM prompts."""

from __future__ import annotations

import re
import unicodedata

_MAX_QUERY_CHARS = 2000
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Zero-width / bidi-override / BOM — invisible payloads that defeat naive filters.
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
_BACKTICK_RE = re.compile(r"`")


def sanitize_query(text: str | None) -> str:
    """Strip control characters and bound length before feeding user text to the LLM.

    Defense in depth against prompt injection payloads delivered via free-text
    fields (query/title) that get interpolated into prompts.

    Order: (1) NFKC normalize so visually-identical chars collapse, (2) strip
    C0 controls, (3) strip invisible unicode, (4) escape XML brackets so the
    user cannot break out of a delimiter, (5) strip backticks, (6) trim and
    cap length.
    """
    if text is None:
        return ""
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = _CONTROL_CHARS_RE.sub(" ", cleaned)
    cleaned = _INVISIBLE_RE.sub("", cleaned)
    cleaned = cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    cleaned = _BACKTICK_RE.sub("", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > _MAX_QUERY_CHARS:
        cleaned = cleaned[:_MAX_QUERY_CHARS]
    return cleaned
