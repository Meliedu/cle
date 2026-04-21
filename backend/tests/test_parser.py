"""Tests for the document parser dispatcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.parser import PageContent, ParseResult, parse_document

SAMPLE_RESULT = ParseResult(
    text="Hello world",
    pages=[PageContent(page_number=1, text="Hello world")],
    word_count=2,
    page_count=1,
)


@pytest.mark.asyncio
async def test_parse_pdf_dispatches_to_pdf_parser():
    with patch(
        "app.services.parser._parse_pdf",
        new_callable=AsyncMock,
        return_value=SAMPLE_RESULT,
    ) as mock_pdf:
        result = await parse_document(b"fake-pdf", "pdf", "test.pdf")

        mock_pdf.assert_awaited_once_with(b"fake-pdf", "test.pdf")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_parse_docx_uses_python_docx_path():
    with patch(
        "app.services.parser._parse_docx", return_value=SAMPLE_RESULT
    ) as mock_docx:
        result = await parse_document(b"fake-docx", "docx", "test.docx")

        mock_docx.assert_called_once_with(b"fake-docx", "test.docx")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_parse_pptx_dispatches_to_pptx_parser():
    with patch(
        "app.services.parser._parse_pptx",
        new_callable=AsyncMock,
        return_value=SAMPLE_RESULT,
    ) as mock_pptx:
        result = await parse_document(b"fake-pptx", "pptx", "test.pptx")

        mock_pptx.assert_awaited_once_with(b"fake-pptx", "test.pptx")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_parse_mp3_dispatches_to_whisper():
    with patch(
        "app.services.parser._transcribe_with_whisper",
        new_callable=AsyncMock,
        return_value=SAMPLE_RESULT,
    ) as mock_whisper:
        result = await parse_document(b"fake-mp3", "mp3", "test.mp3")

        mock_whisper.assert_awaited_once_with(b"fake-mp3", "mp3", "test.mp3")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_parse_mp4_dispatches_to_whisper():
    with patch(
        "app.services.parser._transcribe_with_whisper",
        new_callable=AsyncMock,
        return_value=SAMPLE_RESULT,
    ) as mock_whisper:
        result = await parse_document(b"fake-mp4", "mp4", "test.mp4")

        mock_whisper.assert_awaited_once_with(b"fake-mp4", "mp4", "test.mp4")
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_unsupported_type_raises():
    with pytest.raises(ValueError, match="Unsupported file type: exe"):
        await parse_document(b"fake-exe", "exe", "test.exe")


@pytest.mark.asyncio
async def test_pdf_falls_back_to_pymupdf_when_captions_disabled(monkeypatch):
    """With figure captions off, the Docling path is skipped entirely."""
    from app.services import parser as parser_mod

    monkeypatch.setattr(parser_mod.settings, "enable_figure_captions", False)

    with patch(
        "app.services.parser._parse_pdf_pymupdf", return_value=SAMPLE_RESULT
    ) as mock_pymupdf, patch(
        "app.services.parser._parse_pdf_docling"
    ) as mock_docling:
        result = await parser_mod._parse_pdf(b"fake-pdf", "test.pdf")

        mock_pymupdf.assert_called_once_with(b"fake-pdf", "test.pdf")
        mock_docling.assert_not_called()
        assert result == SAMPLE_RESULT


@pytest.mark.asyncio
async def test_pdf_falls_back_to_pymupdf_when_docling_raises(monkeypatch):
    """A Docling failure should surface as the pymupdf text-only result."""
    from app.services import parser as parser_mod

    monkeypatch.setattr(parser_mod.settings, "enable_figure_captions", True)
    monkeypatch.setattr(parser_mod.settings, "openrouter_api_key", "test-key")

    def _boom(*_a, **_kw):
        raise RuntimeError("docling exploded")

    with patch(
        "app.services.parser._parse_pdf_docling", side_effect=_boom
    ), patch(
        "app.services.parser._parse_pdf_pymupdf", return_value=SAMPLE_RESULT
    ) as mock_pymupdf:
        result = await parser_mod._parse_pdf(b"fake-pdf", "test.pdf")

        mock_pymupdf.assert_called_once_with(b"fake-pdf", "test.pdf")
        assert result == SAMPLE_RESULT


# ---- Page-rescue pass ------------------------------------------------------


@pytest.mark.asyncio
async def test_rescue_low_text_pages_fills_empty_pages(monkeypatch):
    """Pages below page_rescue_min_words get replaced by VLM transcription."""
    from app.services import parser as parser_mod

    # 3 pages: page 1 has full text, page 2 is empty (rescue), page 3 is missing entirely (rescue).
    initial = ParseResult(
        text="A lot of good text on page one.",
        pages=[
            PageContent(page_number=1, text="A lot of good text on page one. " * 10),
            PageContent(page_number=2, text="tiny"),
        ],
        word_count=80,
        page_count=3,
    )

    monkeypatch.setattr(parser_mod, "_pdf_page_count", lambda _: 3)
    monkeypatch.setattr(
        parser_mod, "_render_pdf_pages", lambda data, pns, dpi: [b"png-bytes"] * len(pns)
    )

    async def fake_transcribe(_img):
        return "rescued content for this page " * 5

    monkeypatch.setattr("app.services.vlm.transcribe_page", fake_transcribe)

    result = await parser_mod._rescue_low_text_pdf_pages(initial, b"fake", "test.pdf")

    page_nums = {p.page_number for p in result.pages}
    assert page_nums == {1, 2, 3}
    page_by_num = {p.page_number: p.text for p in result.pages}
    assert "A lot of good text" in page_by_num[1]
    assert "rescued content" in page_by_num[2]
    assert "rescued content" in page_by_num[3]
    assert result.page_count == 3
    assert result.word_count > 0


@pytest.mark.asyncio
async def test_rescue_low_text_pages_noop_when_all_pages_dense(monkeypatch):
    """No VLM calls when every page already has enough text."""
    from app.services import parser as parser_mod

    initial = ParseResult(
        text="x " * 200,
        pages=[PageContent(page_number=1, text="word " * 100)],
        word_count=100,
        page_count=1,
    )
    monkeypatch.setattr(parser_mod, "_pdf_page_count", lambda _: 1)

    calls: list = []

    async def fake_transcribe(_img):
        calls.append(1)
        return "should not happen"

    monkeypatch.setattr("app.services.vlm.transcribe_page", fake_transcribe)
    monkeypatch.setattr(
        parser_mod, "_render_pdf_pages", lambda *a, **k: pytest.fail("no render expected")
    )

    result = await parser_mod._rescue_low_text_pdf_pages(initial, b"fake", "test.pdf")
    assert result is initial
    assert calls == []


@pytest.mark.asyncio
async def test_rescue_low_text_pages_respects_cap(monkeypatch):
    """page_rescue_max_pages caps the number of VLM transcriptions."""
    from app.services import parser as parser_mod
    from app.config import settings

    initial = ParseResult(text="", pages=[], word_count=0, page_count=100)
    monkeypatch.setattr(parser_mod, "_pdf_page_count", lambda _: 100)
    monkeypatch.setattr(settings, "page_rescue_max_pages", 5)

    rendered_counts: list[int] = []

    def fake_render(data, pns, dpi):
        rendered_counts.append(len(pns))
        return [b"img"] * len(pns)

    monkeypatch.setattr(parser_mod, "_render_pdf_pages", fake_render)

    async def fake_transcribe(_img):
        return "rescued"

    monkeypatch.setattr("app.services.vlm.transcribe_page", fake_transcribe)

    result = await parser_mod._rescue_low_text_pdf_pages(initial, b"fake", "test.pdf")
    assert rendered_counts == [5]
    assert len(result.pages) == 5
