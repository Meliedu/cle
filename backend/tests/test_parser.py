"""Tests for the document parser service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.parser import ParseResult, PageContent, parse_document

SAMPLE_RESULT = ParseResult(
    text="Hello world",
    pages=[PageContent(page_number=1, text="Hello world")],
    word_count=2,
    page_count=1,
)


@pytest.mark.asyncio
async def test_parse_pdf():
    with patch(
        "app.services.parser._parse_with_docling",
        new_callable=AsyncMock,
        return_value=SAMPLE_RESULT,
    ) as mock_docling:
        result = await parse_document(b"fake-pdf", "pdf", "test.pdf")

        mock_docling.assert_called_once_with(b"fake-pdf", "pdf", "test.pdf")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_parse_docx():
    with patch(
        "app.services.parser._parse_with_docling",
        new_callable=AsyncMock,
        return_value=SAMPLE_RESULT,
    ) as mock_docling:
        result = await parse_document(b"fake-docx", "docx", "test.docx")

        mock_docling.assert_called_once_with(b"fake-docx", "docx", "test.docx")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_parse_pptx():
    with patch(
        "app.services.parser._parse_with_docling",
        new_callable=AsyncMock,
        return_value=SAMPLE_RESULT,
    ) as mock_docling:
        result = await parse_document(b"fake-pptx", "pptx", "test.pptx")

        mock_docling.assert_called_once_with(b"fake-pptx", "pptx", "test.pptx")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_parse_mp3():
    with patch(
        "app.services.parser._transcribe_with_whisper",
        new_callable=AsyncMock,
        return_value=SAMPLE_RESULT,
    ) as mock_whisper:
        result = await parse_document(b"fake-mp3", "mp3", "test.mp3")

        mock_whisper.assert_called_once_with(b"fake-mp3", "mp3", "test.mp3")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_parse_mp4():
    with patch(
        "app.services.parser._transcribe_with_whisper",
        new_callable=AsyncMock,
        return_value=SAMPLE_RESULT,
    ) as mock_whisper:
        result = await parse_document(b"fake-mp4", "mp4", "test.mp4")

        mock_whisper.assert_called_once_with(b"fake-mp4", "mp4", "test.mp4")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_unsupported_type_raises():
    with pytest.raises(ValueError, match="Unsupported file type: exe"):
        await parse_document(b"fake-exe", "exe", "test.exe")
