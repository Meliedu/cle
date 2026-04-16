"""Tests for the LLM generator service.

All tests mock ``_call_llm`` so no real API calls are made.
"""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.generator import (
    GeneratedFlashcard,
    GeneratedQuestion,
    LLMGenerationError,
    generate_flashcards,
    generate_quiz,
    generate_summary,
)
from app.services.retriever import RetrievedChunk

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_chunks() -> list[RetrievedChunk]:
    doc_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    return [
        RetrievedChunk(
            chunk_id=uuid.UUID("00000000-0000-0000-0000-000000000010"),
            content="Mitochondria are the powerhouses of the cell.",
            document_id=doc_id,
            page_number=1,
            similarity_score=0.95,
        ),
        RetrievedChunk(
            chunk_id=uuid.UUID("00000000-0000-0000-0000-000000000011"),
            content="ATP is produced through oxidative phosphorylation.",
            document_id=doc_id,
            page_number=2,
            similarity_score=0.88,
        ),
    ]


VALID_QUIZ_JSON = json.dumps(
    [
        {
            "question_text": "What is the powerhouse of the cell?",
            "options": {
                "A": "Mitochondria",
                "B": "Nucleus",
                "C": "Ribosome",
                "D": "Golgi apparatus",
            },
            "correct_answer": "A",
            "explanation": "Mitochondria produce ATP, the cell's energy currency.",
        },
        {
            "question_text": "What process produces ATP?",
            "options": {
                "A": "Glycolysis",
                "B": "Oxidative phosphorylation",
                "C": "Fermentation",
                "D": "Photosynthesis",
            },
            "correct_answer": "B",
            "explanation": "Oxidative phosphorylation is the main ATP-producing pathway.",
        },
    ]
)

VALID_FLASHCARD_JSON = json.dumps(
    [
        {
            "front": "What is the powerhouse of the cell?",
            "back": "Mitochondria",
        },
        {
            "front": "How is ATP produced?",
            "back": "Through oxidative phosphorylation.",
        },
    ]
)


# ---------------------------------------------------------------------------
# Quiz tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generates_questions(sample_chunks: list[RetrievedChunk]) -> None:
    with patch(
        "app.services.generator._call_llm",
        new_callable=AsyncMock,
        return_value=VALID_QUIZ_JSON,
    ):
        questions = await generate_quiz(sample_chunks, num_questions=2)

    assert len(questions) == 2
    for q in questions:
        assert isinstance(q, GeneratedQuestion)
        assert q.question_text
        assert set(q.options.keys()) == {"A", "B", "C", "D"}
        assert q.correct_answer in {"A", "B", "C", "D"}
        assert q.explanation


@pytest.mark.asyncio
async def test_handles_invalid_json_with_fallback(
    sample_chunks: list[RetrievedChunk],
) -> None:
    mock_llm = AsyncMock(side_effect=["This is not valid JSON at all", VALID_QUIZ_JSON])

    with patch("app.services.generator._call_llm", mock_llm):
        questions = await generate_quiz(sample_chunks, num_questions=2)

    assert len(questions) == 2
    assert mock_llm.call_count == 2
    for q in questions:
        assert isinstance(q, GeneratedQuestion)


@pytest.mark.asyncio
async def test_raises_llmgeneration_error_when_both_models_fail(
    sample_chunks: list[RetrievedChunk],
) -> None:
    """Both primary and fallback return unparseable JSON.

    We expect an ``LLMGenerationError`` with a safe, user-facing message —
    and crucially we must not leak the raw parser / SDK message out to the
    caller (and from there into ``task.error_message``).
    """
    mock_llm = AsyncMock(
        side_effect=[
            "not json — primary failure",
            "still not json — fallback failure",
        ]
    )

    with patch("app.services.generator._call_llm", mock_llm):
        with pytest.raises(LLMGenerationError) as excinfo:
            await generate_quiz(sample_chunks, num_questions=2)

    # Both models were actually tried.
    assert mock_llm.call_count == 2
    # User-facing message is safe: no "JSON", no "parse", no stack/SDK noise.
    message = str(excinfo.value)
    assert "quiz generation failed" in message
    assert "please try again" in message
    assert "JSON" not in message
    assert "json" not in message
    assert "parse" not in message.lower()


# ---------------------------------------------------------------------------
# Summary tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generates_summary_text(sample_chunks: list[RetrievedChunk]) -> None:
    summary_text = "# Biology Summary\n\n- Mitochondria are the powerhouses of the cell."

    with patch(
        "app.services.generator._call_llm",
        new_callable=AsyncMock,
        return_value=summary_text,
    ):
        result = await generate_summary(sample_chunks)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "Mitochondria" in result


# ---------------------------------------------------------------------------
# Flashcard tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generates_flashcards(sample_chunks: list[RetrievedChunk]) -> None:
    with patch(
        "app.services.generator._call_llm",
        new_callable=AsyncMock,
        return_value=VALID_FLASHCARD_JSON,
    ):
        cards = await generate_flashcards(sample_chunks, num_cards=2)

    assert len(cards) == 2
    for card in cards:
        assert isinstance(card, GeneratedFlashcard)
        assert card.front
        assert card.back
