"""Tests for difficulty-aware revision generation functions."""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.generator import (
    GeneratedFlashcard,
    GeneratedQuestion,
    GeneratedSpeakingTarget,
    generate_revision_flashcards,
    generate_revision_quiz,
    generate_revision_speaking,
)
from app.services.retriever import RetrievedChunk


@pytest.fixture()
def mock_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=uuid.uuid4(),
            content="Photosynthesis converts light energy into chemical energy in plants.",
            document_id=uuid.uuid4(),
            page_number=1,
            similarity_score=0.95,
        ),
    ]


# ---------------------------------------------------------------------------
# Quiz
# ---------------------------------------------------------------------------


class TestGenerateRevisionQuiz:
    @pytest.mark.asyncio()
    async def test_returns_questions_with_correct_count(
        self, mock_chunks: list[RetrievedChunk]
    ) -> None:
        fake_response = json.dumps(
            [
                {
                    "question_text": f"Question {i}",
                    "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
                    "correct_answer": "A",
                    "explanation": "Because A.",
                }
                for i in range(3)
            ]
        )

        with patch(
            "app.services.generator._call_llm", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = fake_response
            result = await generate_revision_quiz(
                mock_chunks, difficulty="medium", num_questions=3
            )

        assert len(result) == 3
        assert all(isinstance(q, GeneratedQuestion) for q in result)
        assert result[0].question_text == "Question 0"

    @pytest.mark.asyncio()
    async def test_difficulty_appears_in_prompt(
        self, mock_chunks: list[RetrievedChunk]
    ) -> None:
        fake_response = json.dumps(
            [
                {
                    "question_text": "Q",
                    "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
                    "correct_answer": "A",
                    "explanation": "E",
                }
            ]
        )

        with patch(
            "app.services.generator._call_llm", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = fake_response
            await generate_revision_quiz(
                mock_chunks, difficulty="hard", num_questions=1
            )

        call_args = mock_llm.call_args
        system_prompt = call_args[0][0] if call_args[0] else call_args[1]["system_prompt"]
        user_prompt = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["user_prompt"]
        combined = system_prompt + user_prompt
        assert "hard" in combined.lower()


# ---------------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------------


class TestGenerateRevisionFlashcards:
    @pytest.mark.asyncio()
    async def test_returns_flashcards(
        self, mock_chunks: list[RetrievedChunk]
    ) -> None:
        fake_response = json.dumps(
            [
                {"front": "What is photosynthesis?", "back": "A process in plants."},
                {"front": "Where does it occur?", "back": "In chloroplasts."},
            ]
        )

        with patch(
            "app.services.generator._call_llm", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = fake_response
            result = await generate_revision_flashcards(
                mock_chunks, difficulty="easy", num_cards=2
            )

        assert len(result) == 2
        assert all(isinstance(fc, GeneratedFlashcard) for fc in result)
        assert result[0].front == "What is photosynthesis?"


# ---------------------------------------------------------------------------
# Speaking
# ---------------------------------------------------------------------------


class TestGenerateRevisionSpeaking:
    @pytest.mark.asyncio()
    async def test_returns_speaking_targets(
        self, mock_chunks: list[RetrievedChunk]
    ) -> None:
        fake_response = json.dumps(
            [
                {"target_text": "Plants use sunlight to make food."},
                {"target_text": "Chlorophyll absorbs light energy."},
            ]
        )

        with patch(
            "app.services.generator._call_llm", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = fake_response
            result = await generate_revision_speaking(
                mock_chunks, difficulty="easy", num_items=2
            )

        assert len(result) == 2
        assert all(isinstance(st, GeneratedSpeakingTarget) for st in result)
        assert result[0].target_text == "Plants use sunlight to make food."
