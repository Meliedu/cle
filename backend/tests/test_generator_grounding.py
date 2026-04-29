"""Tests for generator-level syllabus grounding injection."""

import uuid
from unittest.mock import patch

import pytest

from app.services.generator import generate_quiz
from app.services.retriever import RetrievedChunk


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        content="Big-O describes asymptotic complexity.",
        document_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        page_number=1,
        similarity_score=0.9,
    )


_FAKE_QUIZ_RESPONSE = (
    '[{"question_text":"q","options":{"A":"a"},"correct_answer":"A",'
    '"type":"multiple_choice","difficulty":"easy"}]'
)


@pytest.mark.asyncio
async def test_quiz_generation_includes_grounding_block_when_provided():
    chunks = [_chunk()]
    captured: dict[str, str] = {}

    async def fake_call_llm(system_prompt, user_prompt, model=None):
        captured["user_prompt"] = user_prompt
        return _FAKE_QUIZ_RESPONSE

    with patch("app.services.generator._call_llm", side_effect=fake_call_llm):
        await generate_quiz(
            chunks=chunks,
            num_questions=1,
            grounding_context="Course Learning Outcomes:\n  - Apply Big-O notation",
        )
    assert "<syllabus_grounding>" in captured["user_prompt"]
    assert "Apply Big-O notation" in captured["user_prompt"]


@pytest.mark.asyncio
async def test_quiz_generation_omits_block_when_no_grounding():
    chunks = [_chunk()]
    captured: dict[str, str] = {}

    async def fake_call_llm(system_prompt, user_prompt, model=None):
        captured["user_prompt"] = user_prompt
        return _FAKE_QUIZ_RESPONSE

    with patch("app.services.generator._call_llm", side_effect=fake_call_llm):
        await generate_quiz(chunks=chunks, num_questions=1)
    assert "<syllabus_grounding>" not in captured["user_prompt"]
