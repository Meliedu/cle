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
# Exceptions
# ---------------------------------------------------------------------------


class LLMGenerationError(Exception):
    """Raised when LLM generation fails after all fallback attempts.

    Carries a user-facing message (safe to surface in task ``error_message``)
    and hides any upstream SDK / network detail that should not leak to the
    client.
    """


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratedQuestion:
    question_text: str
    options: dict[str, str]
    correct_answer: str
    explanation: str
    type: str = "multiple_choice"
    difficulty: str = "medium"


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

# Per-chunk and total caps on context sent to the LLM. Large retrieval sets
# or pathological chunks would otherwise blow past model context windows and
# inflate token cost. Numbers are chars, not tokens — generous but finite.
MAX_CHUNK_CHARS = 2000
MAX_CONTEXT_CHARS = 40000


def _build_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a labelled context block.

    Uses ordinal source numbers rather than leaking internal document UUIDs
    to the third-party LLM. Per-chunk content is truncated to
    ``MAX_CHUNK_CHARS`` and the assembled context is truncated to
    ``MAX_CONTEXT_CHARS`` so the prompt stays within bounded size.
    """
    parts: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        content = chunk.content
        if len(content) > MAX_CHUNK_CHARS:
            content = content[:MAX_CHUNK_CHARS]
        parts.append(f"[Source {idx}]\n{content}")
    context = "\n\n".join(parts)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS]
    return context


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

_QUIZ_SYSTEM_PROMPT_BASE = """\
You are an educational quiz generator. Given source material, create quiz questions.
Return ONLY a JSON array of question objects. No extra text.

Each object must have:
- "question_text": the question string
- "type": either "multiple_choice" or "true_false"
- "options": for multiple_choice, an object of N option keys (e.g. "A","B",...) with
  string values. For true_false, exactly {"T": "True", "F": "False"}.
- "correct_answer": one of the option keys (e.g. "A", "C", "T")
- "explanation": a brief explanation of why the answer is correct
- "difficulty": "easy", "medium", or "hard"
"""

_MCQ_LETTERS = ["A", "B", "C", "D", "E", "F"]
MAX_MCQ_OPTIONS = len(_MCQ_LETTERS)


def _quiz_instructions(
    question_types: list[str],
    mcq_option_count: int,
    difficulty: str,
) -> str:
    if mcq_option_count > MAX_MCQ_OPTIONS:
        raise ValueError(
            f"mcq_option_count {mcq_option_count} exceeds MAX_MCQ_OPTIONS {MAX_MCQ_OPTIONS}"
        )
    parts: list[str] = []
    if len(question_types) == 1:
        if question_types[0] == "true_false":
            parts.append(
                'Generate ONLY true/false questions: options must be exactly '
                '{"T": "True", "F": "False"} and correct_answer must be "T" or "F".'
            )
        else:
            letters = ", ".join(f'"{_MCQ_LETTERS[i]}"' for i in range(mcq_option_count))
            parts.append(
                f'Generate ONLY multiple-choice questions with exactly {mcq_option_count} '
                f"options using keys {letters}. correct_answer must be one of those keys."
            )
    else:
        letters = ", ".join(f'"{_MCQ_LETTERS[i]}"' for i in range(mcq_option_count))
        parts.append(
            "Mix true/false and multiple-choice questions. For multiple-choice use "
            f"exactly {mcq_option_count} options with keys {letters}. For true/false "
            'use keys "T" and "F" only.'
        )

    if difficulty == "mixed":
        parts.append(
            "Mix easy, medium, and hard questions roughly evenly. Tag each question "
            'with its difficulty in the "difficulty" field.'
        )
    else:
        parts.append(
            f'All questions should be at **{difficulty}** difficulty. '
            f'Set "difficulty" to "{difficulty}" on every question.'
        )

    return " ".join(parts)


async def generate_quiz(
    chunks: list[RetrievedChunk],
    num_questions: int = 5,
    quiz_type: str = "multiple_choice",  # kept for back-compat; ignored if question_types given
    language: str = "english",
    question_types: list[str] | None = None,
    mcq_option_count: int = 4,
    difficulty: str = "medium",
) -> list[GeneratedQuestion]:
    """Generate quiz questions from retrieved chunks.

    Tries the primary model first. On JSON parse failure, falls back to the
    secondary model. Raises ``LLMGenerationError`` with a safe user-facing
    message if both attempts fail; upstream SDK / parser details are logged
    but never surfaced to the client.
    """
    types = question_types or [quiz_type]
    context = _build_context(chunks)
    instructions = _quiz_instructions(types, mcq_option_count, difficulty)
    user_prompt = (
        f"Create {num_questions} questions about the following {language} language "
        f"learning material. {instructions} "
        f"Write question text and explanations in English. "
        f"Options may include {language} vocabulary/phrases where relevant.\n\n{context}"
    )

    try:
        raw = await _call_llm(_QUIZ_SYSTEM_PROMPT_BASE, user_prompt)
        items = _parse_json_response(raw)
        results = _build_quiz_results(items, difficulty)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        try:
            raw = await _call_llm(
                _QUIZ_SYSTEM_PROMPT_BASE,
                user_prompt,
                model=settings.openrouter_fallback_model,
            )
            items = _parse_json_response(raw)
            results = _build_quiz_results(items, difficulty)
        except Exception as fallback_exc:  # noqa: BLE001 — surface as domain error
            logger.exception("Fallback quiz generation failed")
            raise LLMGenerationError(
                "quiz generation failed; please try again"
            ) from fallback_exc

    return results


def _build_quiz_results(
    items: list[dict], difficulty: str
) -> list[GeneratedQuestion]:
    """Convert parsed LLM items to ``GeneratedQuestion``. Raises ``ValueError``
    on malformed output so the caller can trigger the fallback model path.
    """
    results: list[GeneratedQuestion] = []
    for item in items:
        q_type = item.get("type") or (
            "true_false" if set((item.get("options") or {}).keys()) == {"T", "F"}
            else "multiple_choice"
        )
        q_difficulty = item.get("difficulty", difficulty if difficulty != "mixed" else "medium")
        if q_difficulty not in {"easy", "medium", "hard"}:
            q_difficulty = "medium"
        try:
            question_text = item["question_text"]
            options = item["options"]
            correct_answer = item["correct_answer"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"missing field: {exc}") from exc
        if correct_answer not in options:
            raise ValueError("correct_answer not in options")
        results.append(
            GeneratedQuestion(
                question_text=question_text,
                options=options,
                correct_answer=correct_answer,
                explanation=item.get("explanation", ""),
                type=q_type,
                difficulty=q_difficulty,
            )
        )
    return results


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
    """Generate a markdown summary from retrieved chunks.

    Tries the primary model first. On failure, falls back to the secondary
    model. Raises ``LLMGenerationError`` with a safe user-facing message if
    both attempts fail; upstream SDK / parser details are logged but never
    surfaced to the client.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Summarize the following {language} language learning material. "
        f"Write the summary in English.\n\n{context}"
    )

    try:
        return await _call_llm(_SUMMARY_SYSTEM_PROMPT, user_prompt)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model summary failed: %s — trying fallback", exc)
        try:
            return await _call_llm(
                _SUMMARY_SYSTEM_PROMPT,
                user_prompt,
                model=settings.openrouter_fallback_model,
            )
        except Exception as fallback_exc:  # noqa: BLE001 — surface as domain error
            logger.exception("Fallback summary generation failed")
            raise LLMGenerationError(
                "summary generation failed; please try again"
            ) from fallback_exc


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
    secondary model. Raises ``LLMGenerationError`` with a safe user-facing
    message if both attempts fail; upstream SDK / parser details are logged
    but never surfaced to the client.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_cards} flashcards about the following {language} language learning material. "
        f"Write prompts (front) in English. Answers (back) may include {language} vocabulary/phrases where relevant.\n\n{context}"
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
        except Exception as fallback_exc:  # noqa: BLE001 — surface as domain error
            logger.exception("Fallback flashcard generation failed")
            raise LLMGenerationError(
                "flashcard generation failed; please try again"
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
    secondary model. Raises ``LLMGenerationError`` with a safe user-facing
    message if both attempts fail; upstream SDK / parser details are logged
    but never surfaced to the client.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_questions} multiple-choice questions at **{difficulty}** difficulty "
        f"about the following {language} language learning material. "
        f"Write question text and explanations in English. "
        f"Options may include {language} vocabulary/phrases where relevant.\n\n{context}"
    )

    try:
        raw = await _call_llm(_REVISION_QUIZ_SYSTEM_PROMPT, user_prompt)
        items = _parse_json_response(raw)
        results = _build_revision_quiz_results(items)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        try:
            raw = await _call_llm(
                _REVISION_QUIZ_SYSTEM_PROMPT,
                user_prompt,
                model=settings.openrouter_fallback_model,
            )
            items = _parse_json_response(raw)
            results = _build_revision_quiz_results(items)
        except Exception as fallback_exc:  # noqa: BLE001 — surface as domain error
            logger.exception("Fallback revision quiz generation failed")
            raise LLMGenerationError(
                "revision quiz generation failed; please try again"
            ) from fallback_exc

    return results


def _build_revision_quiz_results(items: list[dict]) -> list[GeneratedQuestion]:
    """Convert parsed LLM items to ``GeneratedQuestion`` for the revision path.
    Raises ``ValueError`` on malformed output so the caller can trigger the
    fallback model path.
    """
    results: list[GeneratedQuestion] = []
    for item in items:
        try:
            question_text = item["question_text"]
            options = item["options"]
            correct_answer = item["correct_answer"]
            explanation = item["explanation"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"missing field: {exc}") from exc
        if correct_answer not in options:
            raise ValueError("correct_answer not in options")
        results.append(
            GeneratedQuestion(
                question_text=question_text,
                options=options,
                correct_answer=correct_answer,
                explanation=explanation,
            )
        )
    return results


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
    secondary model. Raises ``LLMGenerationError`` with a safe user-facing
    message if both attempts fail; upstream SDK / parser details are logged
    but never surfaced to the client.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_cards} flashcards at **{difficulty}** difficulty "
        f"about the following {language} language learning material. "
        f"Write prompts (front) in English. Answers (back) may include {language} vocabulary/phrases where relevant.\n\n{context}"
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
        except Exception as fallback_exc:  # noqa: BLE001 — surface as domain error
            logger.exception("Fallback revision flashcard generation failed")
            raise LLMGenerationError(
                "revision flashcard generation failed; please try again"
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
    secondary model. Raises ``LLMGenerationError`` with a safe user-facing
    message if both attempts fail; upstream SDK / parser details are logged
    but never surfaced to the client.
    """
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_items} speaking practice targets at **{difficulty}** difficulty "
        f"in {language} based on the following material. "
        f"The target_text should be in {language} since the student needs to practice speaking it.\n\n{context}"
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
        except Exception as fallback_exc:  # noqa: BLE001 — surface as domain error
            logger.exception("Fallback revision speaking generation failed")
            raise LLMGenerationError(
                "revision speaking generation failed; please try again"
            ) from fallback_exc

    return [
        GeneratedSpeakingTarget(target_text=item["target_text"])
        for item in items
    ]
