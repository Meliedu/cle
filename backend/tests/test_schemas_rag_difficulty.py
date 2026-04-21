"""Schema-level tests for difficulty on generation requests.

Covers the new difficulty field on flashcards and confirms the existing
difficulty-bearing quiz schema still accepts the full literal set.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.rag import GenerateFlashcardsRequest, GenerateQuizRequest


class TestFlashcardsDifficulty:
    def test_default_is_medium(self):
        req = GenerateFlashcardsRequest(
            course_id=uuid.uuid4(), title="Chapter 1"
        )
        assert req.difficulty == "medium"

    @pytest.mark.parametrize("level", ["easy", "medium", "hard", "mixed"])
    def test_accepts_all_literal_values(self, level: str):
        req = GenerateFlashcardsRequest(
            course_id=uuid.uuid4(),
            title="Vocab",
            difficulty=level,
        )
        assert req.difficulty == level

    def test_rejects_unknown_level(self):
        with pytest.raises(ValidationError):
            GenerateFlashcardsRequest(
                course_id=uuid.uuid4(),
                title="t",
                difficulty="insane",
            )


class TestQuizDifficultyParity:
    @pytest.mark.parametrize("level", ["easy", "medium", "hard", "mixed"])
    def test_quiz_accepts_same_levels(self, level: str):
        req = GenerateQuizRequest(
            course_id=uuid.uuid4(),
            title="Test",
            difficulty=level,
        )
        assert req.difficulty == level
