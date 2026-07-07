"""Per-question grading + shape validation for quiz question types (P5 B7).

``Question.type`` is a free ``String(30)`` with NO DB enum (Decision 2), so
matching / ordering / short_answer are new *renderers* that reuse the existing
columns with NO migration:

- ``multiple_choice`` — ``options`` is the option map; ``correct_answer`` is a
  plain option key; the answer is that key. **UNCHANGED** from the historical
  inline ``answer == correct_answer`` check.
- ``matching`` — ``options`` holds the renderable payload (e.g.
  ``{"left": [...], "right": [...]}``); ``correct_answer`` is a JSON-encoded map
  ``{left_id: right_id}``; the answer is the same map (order-independent).
- ``ordering`` — ``options`` holds the items; ``correct_answer`` is a
  JSON-encoded array of ids in the correct order; the answer is the same array.
- ``short_answer`` — ``correct_answer`` is a JSON-encoded accepted string; the
  answer is the raw typed text, compared after trim + casefold.

``grade_question`` returns ``1.0`` / ``0.0`` and NEVER raises on malformed
stored/posted data (a bad answer simply scores ``0.0``) so a student attempt is
never turned into a 500. Malformed payloads are caught earlier, at question
create/update, by ``validate_question_shape``.
"""
import json
from typing import Any

from fastapi import HTTPException

MULTIPLE_CHOICE = "multiple_choice"
MATCHING = "matching"
ORDERING = "ordering"
SHORT_ANSWER = "short_answer"

SUPPORTED_TYPES = frozenset({MULTIPLE_CHOICE, MATCHING, ORDERING, SHORT_ANSWER})


def _decode_json(value: Any) -> Any:
    """JSON-decode ``value`` if it is a string, else return it unchanged.

    Returns ``None`` when a string cannot be decoded (so callers can treat an
    undecodable payload as "malformed" without a try/except at each call site).
    """
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


def _normalize(text: Any) -> str:
    """Trim + casefold for short-answer exact matching."""
    if text is None:
        return ""
    return str(text).strip().casefold()


def grade_question(question: Any, answer: Any) -> float:
    """Return ``1.0`` if ``answer`` grades correct for ``question``, else ``0.0``.

    ``question`` only needs ``.type`` and ``.correct_answer`` attributes (a real
    ``Question`` row or any duck-typed object). Never raises.
    """
    qtype = getattr(question, "type", None) or MULTIPLE_CHOICE
    correct = getattr(question, "correct_answer", None)

    if qtype == MULTIPLE_CHOICE:
        # Byte-identical to the historical inline `answer == correct_answer`.
        return 1.0 if answer == correct else 0.0

    if qtype == SHORT_ANSWER:
        accepted = _decode_json(correct)
        if accepted is None:
            # Tolerate a plain (non-JSON) stored string.
            accepted = correct
        return 1.0 if _normalize(answer) == _normalize(accepted) else 0.0

    if qtype == MATCHING:
        correct_map = _decode_json(correct)
        answer_map = _decode_json(answer)
        if isinstance(correct_map, dict) and isinstance(answer_map, dict):
            return 1.0 if answer_map == correct_map else 0.0
        return 0.0

    if qtype == ORDERING:
        correct_list = _decode_json(correct)
        answer_list = _decode_json(answer)
        if isinstance(correct_list, list) and isinstance(answer_list, list):
            return 1.0 if answer_list == correct_list else 0.0
        return 0.0

    # Unknown/legacy type: safe exact-match fallback (never raise).
    return 1.0 if answer == correct else 0.0


def validate_question_shape(
    qtype: str, options: Any, correct_answer: Any
) -> None:
    """Reject a malformed ``options`` / ``correct_answer`` for ``qtype``.

    Raises ``HTTPException(422, {"code": "INVALID_QUESTION_SHAPE", ...})`` on a
    malformed payload; returns ``None`` when the shape is valid. Called from
    ``add_question`` / ``update_question`` so ungradeable questions can never be
    stored (Decision 2). ``correct_answer`` stays a JSON-encoded string for the
    new types.
    """

    def _reject(message: str) -> None:
        raise HTTPException(
            status_code=422,  # UNPROCESSABLE (matches service-layer precedent)
            detail={
                "code": "INVALID_QUESTION_SHAPE",
                "message": message,
                "type": qtype,
            },
        )

    if correct_answer is None or (
        isinstance(correct_answer, str) and not correct_answer.strip()
    ):
        _reject("correct_answer is required")

    if qtype == MULTIPLE_CHOICE:
        if not isinstance(options, dict) or not options:
            _reject("multiple_choice requires a non-empty options map")
        if correct_answer not in options:
            _reject("correct_answer must be one of the option keys")
        return

    if qtype == SHORT_ANSWER:
        accepted = _decode_json(correct_answer)
        if accepted is None:
            accepted = correct_answer
        if not isinstance(accepted, str) or not accepted.strip():
            _reject("short_answer correct_answer must be a non-empty string")
        return

    if qtype == MATCHING:
        decoded = _decode_json(correct_answer)
        if not isinstance(decoded, dict) or not decoded:
            _reject("matching correct_answer must be a JSON object of left→right")
        if options is not None and not isinstance(options, dict):
            _reject("matching options must be an object")
        return

    if qtype == ORDERING:
        decoded = _decode_json(correct_answer)
        if not isinstance(decoded, list) or not decoded:
            _reject("ordering correct_answer must be a JSON array of ids")
        if options is not None and not isinstance(options, (dict, list)):
            _reject("ordering options must be an array or object")
        return

    _reject(f"unsupported question type: {qtype}")
