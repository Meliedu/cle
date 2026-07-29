"""Readiness funnel service (spec §4.7): config-driven survey/recommendation.

Phase question sets come from ``pilot.readiness`` (Decision 4), never the DB.
Submitted answers are validated against the config phase's question ids/kinds.
``recommendation`` is computed server-side (no question set) and carries the
pilot's claim-limit copy verbatim so the UI never fabricates a placement
decision. Rows are upserted on ``(user, course, phase)`` — a resubmit overwrites
answers/result/status.

This is a pre-enrollment funnel: submissions carry no concept tags and are a
deliberate data-minimization boundary, so they do NOT emit ``learning_event``s
or enqueue mastery tasks (the evidence seam is course-scoped, post-enrollment).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.readiness import ReadinessResponse
from app.models.user import User
from app.pilot import get_pilot_profile
from app.pilot.base import ReadinessPhaseDef, ReadinessQuestion

# Phases the API accepts beyond the question-backed config phases. ``recommendation``
# is computed server-side (no question set); ``diagnostic`` is optional/skippable
# (CLE ships no question set today) — both remain valid ``phase`` values (Decision 4).
_COMPUTED_PHASES = {"recommendation"}
_OPTIONAL_PHASES = {"diagnostic"}


class ReadinessError(Exception):
    """Typed readiness error. ``code`` is the token the router maps to a response.

    Mirrors ``services.setup.SetupGateError`` — the router layer branches on
    ``code`` (e.g. ``UNKNOWN_PHASE``, ``INVALID_ANSWERS``).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _config_phases() -> dict[str, ReadinessPhaseDef]:
    return {p.phase: p for p in get_pilot_profile().readiness}


def _known_phases() -> set[str]:
    return set(_config_phases()) | _COMPUTED_PHASES | _OPTIONAL_PHASES


def _validate_answers(phase_def: ReadinessPhaseDef, answers: dict[str, Any]) -> None:
    """Validate answer keys/values against the phase's config questions.

    Partial answers are fine (forward-compat: not every question must be
    answered), but every *provided* key must be a known question id and each
    value must match its question kind. ``None`` values are treated as skipped.
    """
    questions: dict[str, ReadinessQuestion] = {q.id: q for q in phase_def.questions}
    scale = get_pilot_profile().confidence_scale
    for key, value in answers.items():
        question = questions.get(key)
        if question is None:
            raise ReadinessError(
                "INVALID_ANSWERS",
                f"Unknown question '{key}' for phase '{phase_def.phase}'",
            )
        if value is None:
            continue
        _validate_value(phase_def.phase, question, value, scale.min, scale.max)


def _validate_value(
    phase: str, question: ReadinessQuestion, value: Any, scale_min: int, scale_max: int
) -> None:
    kind = question.kind
    if kind == "scale":
        # bool is an int subclass but is not a valid scale answer.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ReadinessError(
                "INVALID_ANSWERS", f"'{question.id}' expects a numeric scale value"
            )
        if not (scale_min <= value <= scale_max):
            raise ReadinessError(
                "INVALID_ANSWERS",
                f"'{question.id}' must be within [{scale_min}, {scale_max}]",
            )
    elif kind == "single_choice":
        if value not in question.options:
            raise ReadinessError(
                "INVALID_ANSWERS", f"'{question.id}' must be one of its options"
            )
    elif kind == "multi_choice":
        if not isinstance(value, list) or any(v not in question.options for v in value):
            raise ReadinessError(
                "INVALID_ANSWERS", f"'{question.id}' must be a subset of its options"
            )
    elif kind == "short_text":
        if not isinstance(value, str):
            raise ReadinessError("INVALID_ANSWERS", f"'{question.id}' expects text")


def _recommendation_result(prior_answers: dict[str, dict]) -> dict[str, Any]:
    """Coarse, non-authoritative level hint from ready-check confidence.

    Deliberately simple: average the ``ready_check`` scale answers into a
    3-bucket hint. This is guidance copy, NOT a placement — hence the verbatim
    claim-limit from ``pilot.claim_limits['recommendation']``.
    """
    profile = get_pilot_profile()
    # The recommendation claim-limit is a legal/trust boundary: it is the copy
    # that stops the UI fabricating placement authority. It must NEVER ship
    # empty, so a missing/blank config key is a hard configuration fault rather
    # than a silent default.
    claim_limit = profile.claim_limits.get("recommendation")
    if not claim_limit or not claim_limit.strip():
        raise ReadinessError(
            "MISSING_CLAIM_LIMIT",
            "pilot.claim_limits['recommendation'] is required but missing/empty; "
            "refusing to emit a recommendation without its claim-limit copy.",
        )
    ready = prior_answers.get("ready_check", {}) or {}
    scores = [v for v in ready.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    avg = sum(scores) / len(scores) if scores else 0.0
    if avg < -0.5:
        level_hint = "foundation"
    elif avg < 1.0:
        level_hint = "intermediate"
    else:
        level_hint = "advanced"

    return {
        "level_hint": level_hint,
        "confidence_average": avg,
        "confidence_band": _confidence_band(scores),
        # Per-skill evidence, derived from the answers the learner actually
        # gave. The approved placement result requires every skill result to
        # connect to the recommendation it informs, so the UI can show WHY a
        # level was suggested rather than asserting it. Nothing here is
        # inferred beyond the recorded answers.
        "evidence": _skill_evidence(ready),
        "claim_limit": claim_limit,
    }


#: How consistently the ready-check answers agree. A recommendation drawn from
#: answers that disagree with each other is less trustworthy than one drawn
#: from answers that align, and the UI must be able to say so.
def _confidence_band(scores: list[float]) -> str:
    if len(scores) < 2:
        return "low"
    mean = sum(scores) / len(scores)
    variance = sum((value - mean) ** 2 for value in scores) / len(scores)
    if variance <= 0.5:
        return "high"
    if variance <= 1.5:
        return "medium"
    return "low"


#: `ready_check` question id -> the skill it evidences. Kept here rather than in
#: the pilot profile because it is a property of the recommendation, not of the
#: survey: a pilot may rename prompts without changing what they evidence.
_SKILL_BY_QUESTION: dict[str, str] = {
    "conf_listening": "listening",
    "conf_speaking": "speaking",
    "conf_reading": "reading",
    "conf_writing": "writing",
}


def _skill_evidence(ready: dict[str, Any]) -> list[dict[str, Any]]:
    """One evidence row per answered skill question.

    ``state`` is a coarse, user-safe band the UI renders as words ("Ready",
    "Developing", "Needs support"), never as a score the learner could mistake
    for a grade. Unanswered questions are omitted rather than defaulted, so an
    incomplete survey does not manufacture evidence it does not have.
    """
    rows: list[dict[str, Any]] = []
    for question_id, skill in _SKILL_BY_QUESTION.items():
        value = ready.get(question_id)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if value >= 1.0:
            state = "ready"
        elif value >= -0.5:
            state = "developing"
        else:
            state = "needs_support"
        # No raw score. The docstring above promises the learner never sees a
        # number they could mistake for a grade, and shipping the value in the
        # same payload made that promise depend on every client choosing not to
        # render it. The band is the contract.
        rows.append({"skill": skill, "state": state})
    return rows


async def _existing_answers(
    db: AsyncSession, user: User, course: Course
) -> dict[str, dict]:
    rows = (
        await db.execute(
            select(ReadinessResponse).where(
                ReadinessResponse.user_id == user.id,
                ReadinessResponse.course_id == course.id,
            )
        )
    ).scalars().all()
    return {r.phase: (r.answers or {}) for r in rows}


async def submit_phase(
    db: AsyncSession,
    *,
    user: User,
    course: Course,
    phase: str,
    answers: dict[str, Any],
) -> ReadinessResponse:
    """Upsert a readiness phase response for ``(user, course, phase)``.

    Validates the phase against pilot config, validates answer shape against
    the phase's questions, computes the ``recommendation`` result server-side,
    and upserts (a resubmit overwrites answers/result/status).
    """
    if phase not in _known_phases():
        raise ReadinessError("UNKNOWN_PHASE", f"Unknown readiness phase '{phase}'")

    config_phases = _config_phases()

    if phase in _COMPUTED_PHASES:
        # recommendation has no submitted answers; it is derived from prior phases.
        prior = await _existing_answers(db, user, course)
        result = _recommendation_result(prior)
        answers = {}
    else:
        phase_def = config_phases.get(phase)
        if phase_def is not None:
            _validate_answers(phase_def, answers)
        # Optional phases with no config question set (e.g. diagnostic) skip
        # shape validation — there is nothing to validate against yet.
        result = {}

    stmt = (
        pg_insert(ReadinessResponse)
        .values(
            user_id=user.id,
            course_id=course.id,
            phase=phase,
            answers=answers,
            result=result,
            status="completed",
        )
        .on_conflict_do_update(
            index_elements=["user_id", "course_id", "phase"],
            set_={"answers": answers, "result": result, "status": "completed"},
        )
        .returning(ReadinessResponse.id)
    )
    row_id = (await db.execute(stmt)).scalar_one()
    await db.commit()
    row = await db.get(ReadinessResponse, row_id)
    if row is not None:
        await db.refresh(row)
    return row


async def build_summary(
    db: AsyncSession, *, user: User, course: Course
) -> dict[str, Any]:
    """Assemble all persisted phases + the recommendation (if computed)."""
    rows = (
        await db.execute(
            select(ReadinessResponse).where(
                ReadinessResponse.user_id == user.id,
                ReadinessResponse.course_id == course.id,
            )
        )
    ).scalars().all()
    by_phase = {r.phase: r for r in rows}
    rec = by_phase.get("recommendation")
    return {
        "completed_phases": [p for p, r in by_phase.items() if r.status == "completed"],
        "recommendation": rec.result if rec else None,
        "answers": {p: r.answers for p, r in by_phase.items()},
    }
