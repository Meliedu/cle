import pytest
import uuid
from unittest.mock import patch

from app.services.concept_extraction import (
    extract_candidates_from_chunks,
    CandidateConcept,
)


@pytest.mark.asyncio
async def test_extract_candidates_returns_dataclasses_per_chunk():
    chunks = [
        {"id": uuid.uuid4(), "content": "Big-O notation describes algorithm complexity."},
        {"id": uuid.uuid4(), "content": "Hash tables provide O(1) average-case lookup."},
    ]

    async def fake_llm_extract(text: str) -> list[dict]:
        return [
            {"name": "Big-O Notation", "description": "Asymptotic upper bound."},
            {"name": "Hash Table", "description": "Associative array data structure."},
        ]

    with patch(
        "app.services.concept_extraction._llm_extract_concepts",
        side_effect=fake_llm_extract,
    ):
        result = await extract_candidates_from_chunks(chunks)

    assert len(result) >= 2
    assert all(isinstance(c, CandidateConcept) for c in result)
    names = {c.name for c in result}
    assert "Big-O Notation" in names


@pytest.mark.asyncio
async def test_extract_handles_llm_failure_gracefully():
    chunks = [{"id": uuid.uuid4(), "content": "Foo."}]

    async def fail_llm(text: str) -> list[dict]:
        raise RuntimeError("upstream 503")

    with patch(
        "app.services.concept_extraction._llm_extract_concepts",
        side_effect=fail_llm,
    ):
        result = await extract_candidates_from_chunks(chunks)

    # One bad chunk shouldn't poison the whole job.
    assert result == []


@pytest.mark.asyncio
async def test_extract_truncates_long_description():
    chunks = [{"id": uuid.uuid4(), "content": "Foo."}]
    long_desc = "x" * 3000

    async def fake_llm(text: str) -> list[dict]:
        return [{"name": "TestConcept", "description": long_desc}]

    with patch(
        "app.services.concept_extraction._llm_extract_concepts",
        side_effect=fake_llm,
    ):
        result = await extract_candidates_from_chunks(chunks)

    assert len(result) == 1
    assert result[0].description is not None
    assert len(result[0].description) <= 2000
