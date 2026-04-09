"""LLM generator service for quiz, summary, and flashcard generation.

Uses OpenRouter (OpenAI-compatible API) with primary/fallback model strategy.
"""

import json
import logging
import re
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import settings
from app.services.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratedQuestion:
    question_text: str
    options: dict[str, str]
    correct_answer: str
    explanation: str


@dataclass(frozen=True)
class GeneratedFlashcard:
    front: str
    back: str


# ---------------------------------------------------------------------------
# Client (lazy singleton)
# ---------------------------------------------------------------------------

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client  # noqa: PLW0603
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a labelled context block."""
    parts: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        parts.append(f"[Source {idx}: {chunk.document_id}]\n{chunk.content}")
    return "\n\n".join(parts)


async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> str:
    """Call the OpenRouter chat completions endpoint and return the response text."""
    client = _get_client()
    target_model = model or settings.openrouter_primary_model

    response = await client.chat.completions.create(
        model=target_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )

    content = response.choices[0].message.content
    if content is None:
        raise ValueError(f"LLM returned empty response (model={target_model})")
    return content


def _parse_json_response(text: str) -> list[dict]:
    """Extract a JSON array from an LLM response, handling markdown code blocks."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.strip().rstrip("`")

    # Find the first JSON array in the text
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON array found in response")

    array_text = cleaned[start : end + 1]
    parsed = json.loads(array_text)

    if not isinstance(parsed, list):
        raise ValueError("Parsed JSON is not an array")

    return parsed


# ---------------------------------------------------------------------------
# Quiz Generation
# ---------------------------------------------------------------------------

_QUIZ_SYSTEM_PROMPT = """\
You are an educational quiz generator. Given source material, create quiz questions.
Return ONLY a JSON array of question objects. No extra text.

Each object must have:
- "question_text": the question string
- "options": an object with keys "A", "B", "C", "D" and string values
- "correct_answer": one of "A", "B", "C", "D"
- "explanation": a brief explanation of why the answer is correct
"""


async def generate_quiz(
    chunks: list[RetrievedChunk],
    num_questions: int = 5,
    quiz_type: str = "multiple_choice",
    language: str = "english",
) -> list[GeneratedQuestion]:
    """Generate quiz questions from retrieved chunks.

    Tries the primary model first. On JSON parse failure, falls back to the
    secondary model. Raises ``ValueError`` if both attempts fail.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_questions} {quiz_type} questions in {language} "
        f"based on the following material:\n\n{context}"
    )

    # Attempt primary model
    try:
        raw = await _call_llm(_QUIZ_SYSTEM_PROMPT, user_prompt)
        items = _parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        try:
            raw = await _call_llm(
                _QUIZ_SYSTEM_PROMPT,
                user_prompt,
                model=settings.openrouter_fallback_model,
            )
            items = _parse_json_response(raw)
        except (ValueError, json.JSONDecodeError) as fallback_exc:
            raise ValueError(
                "Both primary and fallback models failed to produce valid quiz JSON"
            ) from fallback_exc

    return [
        GeneratedQuestion(
            question_text=item["question_text"],
            options=item["options"],
            correct_answer=item["correct_answer"],
            explanation=item["explanation"],
        )
        for item in items
    ]


# ---------------------------------------------------------------------------
# Summary Generation
# ---------------------------------------------------------------------------

_SUMMARY_SYSTEM_PROMPT = """\
You are an educational summarizer. Given source material, produce a clear and
concise markdown summary that captures the key concepts, definitions, and
relationships. Use headings, bullet points, and bold text for emphasis.
"""


async def generate_summary(
    chunks: list[RetrievedChunk],
    language: str = "english",
) -> str:
    """Generate a markdown summary from retrieved chunks."""
    context = _build_context(chunks)
    user_prompt = (
        f"Summarize the following material in {language}:\n\n{context}"
    )
    return await _call_llm(_SUMMARY_SYSTEM_PROMPT, user_prompt)


# ---------------------------------------------------------------------------
# Flashcard Generation
# ---------------------------------------------------------------------------

_FLASHCARD_SYSTEM_PROMPT = """\
You are an educational flashcard generator. Given source material, create
flashcards for effective spaced-repetition study.
Return ONLY a JSON array of flashcard objects. No extra text.

Each object must have:
- "front": the question or prompt for the front of the card
- "back": the answer or explanation for the back of the card
"""


async def generate_flashcards(
    chunks: list[RetrievedChunk],
    num_cards: int = 10,
    language: str = "english",
) -> list[GeneratedFlashcard]:
    """Generate flashcards from retrieved chunks.

    Tries the primary model first. On JSON parse failure, falls back to the
    secondary model. Raises ``ValueError`` if both attempts fail.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_cards} flashcards in {language} "
        f"based on the following material:\n\n{context}"
    )

    # Attempt primary model
    try:
        raw = await _call_llm(_FLASHCARD_SYSTEM_PROMPT, user_prompt)
        items = _parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        try:
            raw = await _call_llm(
                _FLASHCARD_SYSTEM_PROMPT,
                user_prompt,
                model=settings.openrouter_fallback_model,
            )
            items = _parse_json_response(raw)
        except (ValueError, json.JSONDecodeError) as fallback_exc:
            raise ValueError(
                "Both primary and fallback models failed to produce valid flashcard JSON"
            ) from fallback_exc

    return [
        GeneratedFlashcard(front=item["front"], back=item["back"])
        for item in items
    ]


# ---------------------------------------------------------------------------
# Dataclass — Speaking Target
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratedSpeakingTarget:
    target_text: str


# ---------------------------------------------------------------------------
# Difficulty-Aware Revision: Quiz
# ---------------------------------------------------------------------------

_REVISION_QUIZ_SYSTEM_PROMPT = """\
You are an educational quiz generator that adapts question difficulty.
Given source material and a difficulty level, create quiz questions.
Return ONLY a JSON array of question objects. No extra text.

Difficulty levels:
- easy: recall-based questions — identify facts, definitions, and terms directly from the material
- medium: application-based questions — apply concepts to new scenarios or examples
- hard: analysis/synthesis questions — compare, evaluate, combine ideas, or draw inferences

Each object must have:
- "question_text": the question string
- "options": an object with keys "A", "B", "C", "D" and string values
- "correct_answer": one of "A", "B", "C", "D"
- "explanation": a brief explanation of why the answer is correct
"""


async def generate_revision_quiz(
    chunks: list[RetrievedChunk],
    difficulty: str,
    num_questions: int = 7,
    language: str = "english",
) -> list[GeneratedQuestion]:
    """Generate difficulty-aware quiz questions from retrieved chunks.

    Tries the primary model first. On JSON parse failure, falls back to the
    secondary model. Raises ``ValueError`` if both attempts fail.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_questions} multiple-choice questions at **{difficulty}** "
        f"difficulty in {language} based on the following material:\n\n{context}"
    )

    try:
        raw = await _call_llm(_REVISION_QUIZ_SYSTEM_PROMPT, user_prompt)
        items = _parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        try:
            raw = await _call_llm(
                _REVISION_QUIZ_SYSTEM_PROMPT,
                user_prompt,
                model=settings.openrouter_fallback_model,
            )
            items = _parse_json_response(raw)
        except (ValueError, json.JSONDecodeError) as fallback_exc:
            raise ValueError(
                "Both primary and fallback models failed to produce valid revision quiz JSON"
            ) from fallback_exc

    return [
        GeneratedQuestion(
            question_text=item["question_text"],
            options=item["options"],
            correct_answer=item["correct_answer"],
            explanation=item["explanation"],
        )
        for item in items
    ]


# ---------------------------------------------------------------------------
# Difficulty-Aware Revision: Flashcards
# ---------------------------------------------------------------------------

_REVISION_FLASHCARD_SYSTEM_PROMPT = """\
You are an educational flashcard generator that adapts card difficulty.
Given source material and a difficulty level, create flashcards for spaced-repetition study.
Return ONLY a JSON array of flashcard objects. No extra text.

Difficulty levels:
- easy: term/definition pairs — straightforward vocabulary and key facts
- medium: conceptual cards — explain relationships, processes, or cause-and-effect
- hard: nuanced/edge-case cards — subtle distinctions, exceptions, and advanced implications

Each object must have:
- "front": the question or prompt for the front of the card
- "back": the answer or explanation for the back of the card
"""


async def generate_revision_flashcards(
    chunks: list[RetrievedChunk],
    difficulty: str,
    num_cards: int = 7,
    language: str = "english",
) -> list[GeneratedFlashcard]:
    """Generate difficulty-aware flashcards from retrieved chunks.

    Tries the primary model first. On JSON parse failure, falls back to the
    secondary model. Raises ``ValueError`` if both attempts fail.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_cards} flashcards at **{difficulty}** difficulty in {language} "
        f"based on the following material:\n\n{context}"
    )

    try:
        raw = await _call_llm(_REVISION_FLASHCARD_SYSTEM_PROMPT, user_prompt)
        items = _parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        try:
            raw = await _call_llm(
                _REVISION_FLASHCARD_SYSTEM_PROMPT,
                user_prompt,
                model=settings.openrouter_fallback_model,
            )
            items = _parse_json_response(raw)
        except (ValueError, json.JSONDecodeError) as fallback_exc:
            raise ValueError(
                "Both primary and fallback models failed to produce valid revision flashcard JSON"
            ) from fallback_exc

    return [
        GeneratedFlashcard(front=item["front"], back=item["back"])
        for item in items
    ]


# ---------------------------------------------------------------------------
# Difficulty-Aware Revision: Speaking
# ---------------------------------------------------------------------------

_REVISION_SPEAKING_SYSTEM_PROMPT = """\
You are a language-learning speaking exercise generator that adapts to difficulty.
Given source material and a difficulty level, create target sentences or passages
for the student to practise speaking aloud.
Return ONLY a JSON array of speaking-target objects. No extra text.

Difficulty levels:
- easy: short, simple sentences using basic vocabulary from the material
- medium: compound sentences that combine two or more ideas from the material
- hard: complex paragraphs with subordinate clauses, transitions, and nuanced phrasing

Each object must have:
- "target_text": the sentence or passage the student should read/speak aloud
"""


async def generate_revision_speaking(
    chunks: list[RetrievedChunk],
    difficulty: str,
    num_items: int = 6,
    language: str = "english",
) -> list[GeneratedSpeakingTarget]:
    """Generate difficulty-aware speaking targets from retrieved chunks.

    Tries the primary model first. On JSON parse failure, falls back to the
    secondary model. Raises ``ValueError`` if both attempts fail.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_items} speaking practice targets at **{difficulty}** "
        f"difficulty in {language} based on the following material:\n\n{context}"
    )

    try:
        raw = await _call_llm(_REVISION_SPEAKING_SYSTEM_PROMPT, user_prompt)
        items = _parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        try:
            raw = await _call_llm(
                _REVISION_SPEAKING_SYSTEM_PROMPT,
                user_prompt,
                model=settings.openrouter_fallback_model,
            )
            items = _parse_json_response(raw)
        except (ValueError, json.JSONDecodeError) as fallback_exc:
            raise ValueError(
                "Both primary and fallback models failed to produce valid revision speaking JSON"
            ) from fallback_exc

    return [
        GeneratedSpeakingTarget(target_text=item["target_text"])
        for item in items
    ]
