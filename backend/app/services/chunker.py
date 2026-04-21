"""Pure-function text chunker that splits text into overlapping, sentence-aligned chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class PageContent:
    page_number: int
    text: str


@dataclass(frozen=True)
class ChunkData:
    content: str
    chunk_index: int
    page_number: int | None
    token_count: int
    metadata: dict = field(default_factory=dict)


_FIGURE_MARKER = "[Figure:"


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.?!])\s+|\n{2,}")

TARGET_TOKENS = 500
OVERLAP_TOKENS = 75
MAX_TOKENS = 550


def _count_tokens(text: str) -> int:
    return len(_enc.encode(text, disallowed_special=()))


def _split_sentences(text: str) -> list[str]:
    """Split text on sentence boundaries while preserving content."""
    parts = _SENTENCE_BOUNDARY.split(text)
    return [s for s in parts if s.strip()]


def _resolve_page(char_offset: int, page_ranges: list[tuple[int, int, int]]) -> int | None:
    """Return the page number for a character offset, or None."""
    for start, end, page_num in page_ranges:
        if start <= char_offset < end:
            return page_num
    return None


def _build_page_ranges(pages: list[PageContent]) -> tuple[str, list[tuple[int, int, int]]]:
    """Concatenate page texts and record (start, end, page_number) ranges."""
    combined_parts: list[str] = []
    ranges: list[tuple[int, int, int]] = []
    offset = 0
    for page in pages:
        text = page.text
        combined_parts.append(text)
        ranges.append((offset, offset + len(text), page.page_number))
        offset += len(text) + 1  # +1 for the joining newline
    return "\n".join(combined_parts), ranges


def chunk_text(
    text: str,
    pages: list[PageContent] | None = None,
) -> list[ChunkData]:
    """Split *text* into ~500-token chunks with 75-token overlap on sentence boundaries.

    When *pages* is provided the function concatenates page texts itself and
    resolves a page number for each chunk based on where its first character falls.
    """
    page_ranges: list[tuple[int, int, int]] = []

    if pages is not None:
        text, page_ranges = _build_page_ranges(pages)

    if not text or not text.strip():
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    # Map each sentence back to its character offset in the original text.
    sentence_offsets: list[int] = []
    search_start = 0
    for sentence in sentences:
        idx = text.find(sentence, search_start)
        sentence_offsets.append(idx if idx != -1 else search_start)
        if idx != -1:
            search_start = idx + len(sentence)

    chunks: list[ChunkData] = []
    chunk_index = 0
    i = 0  # sentence index

    while i < len(sentences):
        # Build a chunk up to TARGET_TOKENS.
        chunk_sentences: list[str] = []
        token_count = 0
        start_i = i

        while i < len(sentences):
            s_tokens = _count_tokens(sentences[i])
            if token_count + s_tokens > MAX_TOKENS and chunk_sentences:
                break
            chunk_sentences.append(sentences[i])
            token_count += s_tokens
            i += 1

        content = " ".join(chunk_sentences)

        page_number: int | None = None
        if page_ranges:
            page_number = _resolve_page(sentence_offsets[start_i], page_ranges)

        metadata: dict = {}
        if _FIGURE_MARKER in content:
            metadata["has_figure"] = True

        chunks.append(
            ChunkData(
                content=content,
                chunk_index=chunk_index,
                page_number=page_number,
                token_count=_count_tokens(content),
                metadata=metadata,
            )
        )
        chunk_index += 1

        # Rewind by overlap: step back through sentences until we've covered
        # OVERLAP_TOKENS. Always include at least one sentence, and include
        # the sentence that pushes us over the threshold — otherwise any
        # trailing sentence longer than OVERLAP_TOKENS silently produced
        # zero overlap between consecutive chunks.
        #
        # Forward-progress guard: we must advance by at least one sentence
        # per outer iteration, otherwise a single oversized sentence (long
        # VLM transcription, a paragraph with no .?! punctuation) makes the
        # rewind put `i` back at `start_i` and the outer loop spins forever.
        # Cap rewind at (i - start_i - 1) so at least one sentence stays
        # "consumed" per iteration.
        if i < len(sentences):
            overlap_tokens = 0
            rewind = 0
            for j in range(i - 1, start_i - 1, -1):
                s_tokens = _count_tokens(sentences[j])
                overlap_tokens += s_tokens
                rewind += 1
                if overlap_tokens >= OVERLAP_TOKENS:
                    break
            max_rewind = (i - start_i) - 1
            if rewind > max_rewind:
                rewind = max_rewind
            if rewind > 0:
                i -= rewind

    return chunks
