"""Document parser service.

Dispatches to Docling (pdf/docx/pptx) or Whisper (mp3/mp4) based on file type.
"""

from __future__ import annotations

import asyncio
import io
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import openai

from app.config import settings

DOCLING_TYPES = {"pdf", "docx", "pptx"}
WHISPER_TYPES = {"mp3", "mp4"}


@dataclass(frozen=True)
class PageContent:
    page_number: int
    text: str


@dataclass(frozen=True)
class ParseResult:
    text: str
    pages: list[PageContent] = field(default_factory=list)
    word_count: int = 0
    page_count: int = 0


async def parse_document(
    file_data: bytes,
    file_type: str,
    filename: str,
) -> ParseResult:
    """Parse a document and return its text content.

    Args:
        file_data: Raw bytes of the uploaded file.
        file_type: Extension without dot (e.g. "pdf", "mp3").
        filename: Original filename for metadata.

    Returns:
        ParseResult with extracted text, per-page content, and counts.

    Raises:
        ValueError: If the file type is not supported.
    """
    normalized = file_type.lower().lstrip(".")

    if normalized in DOCLING_TYPES:
        return await _parse_with_docling(file_data, normalized, filename)

    if normalized in WHISPER_TYPES:
        return await _transcribe_with_whisper(file_data, normalized, filename)

    raise ValueError(f"Unsupported file type: {file_type}")


def _docling_sync(file_data: bytes, file_type: str, filename: str) -> ParseResult:
    """Synchronous Docling conversion (runs in a thread)."""
    from docling.document_converter import DocumentConverter

    suffix = f".{file_type}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name

    try:
        converter = DocumentConverter()
        doc = converter.convert(tmp_path)

        full_text = doc.document.export_to_markdown()

        pages: dict[int, list[str]] = {}
        for item, _level in doc.document.iterate_items():
            prov = getattr(item, "prov", None)
            if prov:
                for loc in prov:
                    page_no = getattr(loc, "page_no", None)
                    if page_no is not None:
                        pages.setdefault(page_no, []).append(item.text if hasattr(item, "text") else "")

        page_contents = [
            PageContent(page_number=pn, text="\n".join(texts))
            for pn, texts in sorted(pages.items())
        ]

        word_count = len(full_text.split())
        page_count = len(page_contents) if page_contents else 1

        return ParseResult(
            text=full_text,
            pages=page_contents,
            word_count=word_count,
            page_count=page_count,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def _parse_with_docling(
    file_data: bytes,
    file_type: str,
    filename: str,
) -> ParseResult:
    """Parse pdf/docx/pptx using the Docling library."""
    return await asyncio.to_thread(_docling_sync, file_data, file_type, filename)


async def _transcribe_with_whisper(
    file_data: bytes,
    file_type: str,
    filename: str,
) -> ParseResult:
    """Transcribe mp3/mp4 using OpenAI Whisper."""
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    audio_file = io.BytesIO(file_data)
    audio_file.name = filename

    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="text",
    )

    text = str(transcript)
    word_count = len(text.split())

    return ParseResult(
        text=text,
        pages=[PageContent(page_number=1, text=text)],
        word_count=word_count,
        page_count=1,
    )
