"""Document parser service.

Dispatches to PyMuPDF (pdf), python-docx (docx), python-pptx (pptx),
or Whisper (mp3/mp4) based on file type.
"""

from __future__ import annotations

import asyncio
import io
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import openai

from app.config import settings

DOCX_TYPE = "docx"
PPTX_TYPE = "pptx"
PDF_TYPE = "pdf"
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
    """Parse a document and return its text content."""
    normalized = file_type.lower().lstrip(".")

    if normalized == PDF_TYPE:
        return await asyncio.to_thread(_parse_pdf, file_data, filename)

    if normalized == DOCX_TYPE:
        return await asyncio.to_thread(_parse_docx, file_data, filename)

    if normalized == PPTX_TYPE:
        return await asyncio.to_thread(_parse_pptx, file_data, filename)

    if normalized in WHISPER_TYPES:
        return await _transcribe_with_whisper(file_data, normalized, filename)

    raise ValueError(f"Unsupported file type: {file_type}")


def _parse_pdf(file_data: bytes, filename: str) -> ParseResult:
    """Extract text from PDF using PyMuPDF with markdown output."""
    import pymupdf
    import pymupdf4llm

    doc = pymupdf.open(stream=file_data, filetype="pdf")
    try:
        page_chunks = pymupdf4llm.to_markdown(doc, page_chunks=True)

        pages: list[PageContent] = []
        full_parts: list[str] = []

        for chunk in page_chunks:
            page_num = chunk.get("metadata", {}).get("page", 0) + 1
            text = chunk.get("text", "").strip()
            if text:
                pages.append(PageContent(page_number=page_num, text=text))
                full_parts.append(text)

        full_text = "\n\n".join(full_parts)
        return ParseResult(
            text=full_text,
            pages=pages,
            word_count=len(full_text.split()),
            page_count=len(pages) or 1,
        )
    finally:
        doc.close()


def _parse_docx(file_data: bytes, filename: str) -> ParseResult:
    """Extract text from DOCX using python-docx."""
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(file_data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    full_text = "\n\n".join(paragraphs)

    return ParseResult(
        text=full_text,
        pages=[PageContent(page_number=1, text=full_text)],
        word_count=len(full_text.split()),
        page_count=1,
    )


def _parse_pptx(file_data: bytes, filename: str) -> ParseResult:
    """Extract text from PPTX using python-pptx."""
    from pptx import Presentation

    prs = Presentation(io.BytesIO(file_data))
    pages: list[PageContent] = []

    for slide_num, slide in enumerate(prs.slides, 1):
        texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = para.text.strip()
                    if text:
                        texts.append(text)
        if texts:
            slide_text = "\n".join(texts)
            pages.append(PageContent(page_number=slide_num, text=slide_text))

    full_text = "\n\n".join(p.text for p in pages)
    return ParseResult(
        text=full_text,
        pages=pages,
        word_count=len(full_text.split()),
        page_count=len(pages) or 1,
    )


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
