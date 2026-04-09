"""Tests for hybrid retrieval: rrf_merge and fulltext_retrieve."""

from __future__ import annotations

import uuid

import pytest

from app.services.retriever import RetrievedChunk, rrf_merge


def _make_chunk(
    *,
    chunk_id: uuid.UUID | None = None,
    content: str = "test content",
    document_id: uuid.UUID | None = None,
    page_number: int | None = 1,
    similarity_score: float = 0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id or uuid.uuid4(),
        content=content,
        document_id=document_id or uuid.uuid4(),
        page_number=page_number,
        similarity_score=similarity_score,
    )


class TestRRFMerge:
    """Unit tests for rrf_merge."""

    def test_rrf_merge_combines_both_lists(self) -> None:
        """Chunk present in both lists should have the highest RRF score."""
        shared_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        shared_chunk_vec = _make_chunk(
            chunk_id=shared_id,
            document_id=doc_id,
            content="shared chunk",
            similarity_score=0.95,
        )
        shared_chunk_txt = _make_chunk(
            chunk_id=shared_id,
            document_id=doc_id,
            content="shared chunk",
            similarity_score=0.8,
        )

        vec_only = _make_chunk(content="vector only", similarity_score=0.90)
        txt_only = _make_chunk(content="text only", similarity_score=0.85)

        vector_results = [shared_chunk_vec, vec_only]
        text_results = [shared_chunk_txt, txt_only]

        merged = rrf_merge(vector_results, text_results, k=60, top_k=10)

        assert len(merged) == 3
        # The shared chunk should rank first because it appears in both lists
        assert merged[0].chunk_id == shared_id
        # Its RRF score should be the sum of both contributions
        expected_score = 1.0 / (60 + 0 + 1) + 1.0 / (60 + 0 + 1)
        assert merged[0].similarity_score == pytest.approx(expected_score)

    def test_rrf_merge_respects_top_k(self) -> None:
        """Merged result should be limited to top_k items."""
        vector_results = [_make_chunk(content=f"vec-{i}") for i in range(5)]
        text_results = [_make_chunk(content=f"txt-{i}") for i in range(5)]

        merged = rrf_merge(vector_results, text_results, k=60, top_k=3)

        assert len(merged) == 3

    def test_rrf_merge_empty_inputs(self) -> None:
        """Empty inputs should produce an empty result."""
        assert rrf_merge([], [], k=60, top_k=10) == []

    def test_rrf_merge_one_empty_list(self) -> None:
        """When one list is empty, result should come solely from the other."""
        chunks = [_make_chunk(content=f"chunk-{i}") for i in range(3)]

        merged_vec_only = rrf_merge(chunks, [], k=60, top_k=10)
        assert len(merged_vec_only) == 3

        merged_txt_only = rrf_merge([], chunks, k=60, top_k=10)
        assert len(merged_txt_only) == 3

    def test_rrf_merge_preserves_chunk_data(self) -> None:
        """Merged chunks should retain content, document_id, and page_number."""
        chunk_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        chunk = _make_chunk(
            chunk_id=chunk_id,
            document_id=doc_id,
            content="important content",
            page_number=42,
            similarity_score=0.99,
        )

        merged = rrf_merge([chunk], [], k=60, top_k=10)

        assert len(merged) == 1
        assert merged[0].chunk_id == chunk_id
        assert merged[0].document_id == doc_id
        assert merged[0].content == "important content"
        assert merged[0].page_number == 42

    def test_rrf_merge_ranking_order(self) -> None:
        """Chunks appearing earlier in input lists should score higher."""
        chunks_a = [_make_chunk(content=f"a-{i}") for i in range(3)]
        chunks_b: list[RetrievedChunk] = []

        merged = rrf_merge(chunks_a, chunks_b, k=60, top_k=10)

        # Scores should be strictly decreasing
        for i in range(len(merged) - 1):
            assert merged[i].similarity_score > merged[i + 1].similarity_score


class TestFulltextRetrieve:
    """Placeholder integration tests for fulltext_retrieve.

    Full integration tests require a running PostgreSQL instance with
    tsvector columns populated. These are marked as pass-through for now.
    """

    def test_fulltext_retrieve_placeholder(self) -> None:
        """Placeholder: fulltext_retrieve requires a live database."""
        # Integration test — needs PostgreSQL with tsvector trigger.
        # Will be covered by E2E / integration test suite.
        pass
