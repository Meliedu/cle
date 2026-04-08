"""Tests for the text chunker service."""

import pytest

from app.services.chunker import ChunkData, PageContent, chunk_text


class TestShortText:
    """Short text that fits in a single chunk."""

    def test_single_chunk(self) -> None:
        text = "This is a short document. It has only a few sentences."
        result = chunk_text(text)

        assert len(result) == 1
        assert result[0].chunk_index == 0
        assert result[0].token_count <= 550
        assert result[0].page_number is None

    def test_single_chunk_content_preserved(self) -> None:
        text = "Hello world. Goodbye world."
        result = chunk_text(text)
        assert "Hello world" in result[0].content
        assert "Goodbye world" in result[0].content


class TestMultipleChunks:
    """~1000 words should produce multiple chunks each <= 550 tokens."""

    @pytest.fixture()
    def long_text(self) -> str:
        sentence = "The quick brown fox jumps over the lazy dog near the river bank. "
        # Each sentence is ~13 tokens; ~77 repetitions ≈ 1001 tokens
        return sentence * 77

    def test_produces_multiple_chunks(self, long_text: str) -> None:
        result = chunk_text(long_text)
        assert len(result) >= 2

    def test_each_chunk_within_token_limit(self, long_text: str) -> None:
        result = chunk_text(long_text)
        for chunk in result:
            assert chunk.token_count <= 550, (
                f"Chunk {chunk.chunk_index} has {chunk.token_count} tokens"
            )

    def test_chunk_indices_sequential(self, long_text: str) -> None:
        result = chunk_text(long_text)
        for i, chunk in enumerate(result):
            assert chunk.chunk_index == i


class TestOverlap:
    """Consecutive chunks should share overlapping content."""

    def test_overlap_exists(self) -> None:
        sentence = "The quick brown fox jumps over the lazy dog near the river bank. "
        text = sentence * 77
        result = chunk_text(text)

        assert len(result) >= 2

        for idx in range(len(result) - 1):
            current_tokens = set(result[idx].content.split())
            next_tokens = set(result[idx + 1].content.split())
            overlap = current_tokens & next_tokens
            assert len(overlap) > 0, (
                f"No overlap between chunk {idx} and chunk {idx + 1}"
            )


class TestPageNumbers:
    """Page numbers should be preserved when pages are provided."""

    def test_page_numbers_assigned(self) -> None:
        pages = [
            PageContent(page_number=1, text="First page content here. It discusses the introduction."),
            PageContent(page_number=2, text="Second page content here. It covers the methodology."),
        ]
        result = chunk_text(text="", pages=pages)

        assert len(result) >= 1
        assert all(chunk.page_number is not None for chunk in result)

    def test_page_numbers_correct_for_multi_page(self) -> None:
        sentence = "This sentence has about ten words in it total here. "
        page1_text = sentence * 50  # ~500 tokens
        page2_text = sentence * 50

        pages = [
            PageContent(page_number=1, text=page1_text),
            PageContent(page_number=2, text=page2_text),
        ]
        result = chunk_text(text="", pages=pages)

        assert len(result) >= 2

        # First chunk should reference page 1
        assert result[0].page_number == 1

        # At least one chunk should reference page 2
        page_2_chunks = [c for c in result if c.page_number == 2]
        assert len(page_2_chunks) >= 1

    def test_no_pages_gives_none(self) -> None:
        text = "A simple sentence. Another one."
        result = chunk_text(text)
        for chunk in result:
            assert chunk.page_number is None


class TestEmptyInput:
    """Empty or whitespace-only input should return an empty list."""

    def test_empty_string(self) -> None:
        assert chunk_text("") == []

    def test_whitespace_only(self) -> None:
        assert chunk_text("   \n\t\n   ") == []

    def test_none_pages_empty_text(self) -> None:
        assert chunk_text("", pages=None) == []


class TestSentenceBoundaries:
    """Chunks should end at sentence boundaries, not mid-sentence."""

    def test_chunks_end_at_sentence_boundary(self) -> None:
        sentences = [
            f"Sentence number {i} provides important information about the topic at hand. "
            for i in range(100)
        ]
        text = "".join(sentences)
        result = chunk_text(text)

        assert len(result) >= 2

        for chunk in result:
            content = chunk.content.strip()
            # Each chunk should end with sentence-ending punctuation
            assert content[-1] in ".?!", (
                f"Chunk {chunk.chunk_index} does not end at a sentence boundary: "
                f"...{content[-30:]!r}"
            )

    def test_question_mark_boundary(self) -> None:
        sentence_a = "What is the meaning of life? " * 50
        sentence_b = "Nobody knows the answer to that question. " * 50
        text = sentence_a + sentence_b
        result = chunk_text(text)

        assert len(result) >= 2
        for chunk in result:
            content = chunk.content.strip()
            assert content[-1] in ".?!"

    def test_exclamation_boundary(self) -> None:
        sentence = "This is truly absolutely amazing and wonderful! " * 80
        other = "Truly wonderful things happen every single day around here. " * 80
        text = sentence + other
        result = chunk_text(text)

        assert len(result) >= 2
        for chunk in result:
            content = chunk.content.strip()
            assert content[-1] in ".?!"


class TestDataclasses:
    """Verify dataclass immutability and fields."""

    def test_chunk_data_frozen(self) -> None:
        chunk = ChunkData(content="test", chunk_index=0, page_number=None, token_count=1)
        with pytest.raises(AttributeError):
            chunk.content = "modified"  # type: ignore[misc]

    def test_page_content_frozen(self) -> None:
        page = PageContent(page_number=1, text="hello")
        with pytest.raises(AttributeError):
            page.text = "modified"  # type: ignore[misc]
