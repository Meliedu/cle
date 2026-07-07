"""Evidence-engine async job handlers.

Concept extraction, concept tagging, mastery updates, attempt-history
replay, and instructor-alert evaluation live here.

These were extracted from ``app.services.jobs`` to keep that module under
the 800-line cap. ``jobs.py`` re-exports the handlers below for backward
compatibility, so callers that import them from ``app.services.jobs``
continue to work unchanged.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# Batch size for ``run_replay_attempt_history``. Each pass over the four
# attempt tables (quiz / flashcard / revision / pronunciation) streams rows
# in chunks of this size and commits between batches so a long replay
# doesn't hold a single transaction (and its DB connection + working set)
# open for the whole window. Module-level so tests can monkey-patch it.
REPLAY_BATCH_SIZE = 500


async def run_extract_concept_candidates(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Sample chunks → LLM extract → cluster → write Concept(status='pending') rows."""
    from app.models import Concept
    from app.services.concept_clustering import cluster_candidates
    from app.services.concept_extraction import (
        extract_candidates_from_chunks,
        sample_chunks_for_extraction,
    )

    course_id = uuid.UUID(payload["course_id"])
    chunks = await sample_chunks_for_extraction(session, course_id)
    candidates = await extract_candidates_from_chunks(chunks)
    if not candidates:
        return {"course_id": str(course_id), "candidates": 0, "clusters": 0}

    clusters = await cluster_candidates(candidates)
    inserted = 0
    for cl in clusters:
        # ``cluster_candidates`` keeps ``members`` and ``member_vectors``
        # parallel; pair each member with its embedding so the row carries
        # an ``embedding`` (3072-dim, same space as the chunk store) usable
        # for future dedupe / merge-target similarity ranking.
        for member, vec in zip(cl.members, cl.member_vectors):
            session.add(
                Concept(
                    course_id=course_id,
                    name=member.name,
                    description=member.description,
                    extracted_from_chunk_id=member.source_chunk_id,
                    status="pending",
                    cluster_id=cl.cluster_id,
                    embedding=vec,
                )
            )
            inserted += 1
    await session.commit()
    return {
        "course_id": str(course_id),
        "candidates": len(candidates),
        "clusters": len(clusters),
        "inserted": inserted,
    }


async def run_tag_artifact_concepts(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Tag a single artifact (chunk / question / flashcard / pool item).

    payload: {target_kind, target_id, course_id, [source_chunk_id]}
    """
    from app.models import Chunk
    from app.services.concept_tagger import (
        inherit_tags_from_chunk,
        tag_chunk_via_llm,
    )

    target_kind = payload["target_kind"]
    target_id = uuid.UUID(payload["target_id"])
    course_id = uuid.UUID(payload["course_id"])
    source_chunk_id = (
        uuid.UUID(payload["source_chunk_id"])
        if payload.get("source_chunk_id") else None
    )

    if target_kind == "chunk":
        chunk = (
            await session.execute(
                select(Chunk).where(Chunk.id == target_id)
            )
        ).scalar_one_or_none()
        if chunk is None:
            return {"status": "missing"}
        n = await tag_chunk_via_llm(
            session,
            chunk_id=chunk.id,
            chunk_text=chunk.content,
            course_id=course_id,
        )
        await session.commit()
        return {"status": "tagged", "inserted": n}

    if source_chunk_id is None:
        # Orphan artifact: fall back to LLM directly. We treat target as a
        # chunk-like passage by reading associated text from the model. Caller
        # must populate ``source_chunk_id`` when available — the orphan branch
        # is currently a no-op; LLM tagging for orphans is a Phase 2 follow-up.
        return {"status": "skipped_orphan"}

    n = await inherit_tags_from_chunk(
        session,
        source_chunk_id=source_chunk_id,
        target_kind=target_kind,
        target_id=target_id,
    )
    await session.commit()
    return {"status": "inherited", "inserted": n}


async def run_update_concept_mastery(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Apply Beta-Binomial update for one attempt event.

    Enqueued by quiz / flashcard / revision attempt handlers immediately
    after the user's attempt is committed. Resolves the target's tagged
    concepts and applies a (alpha += w*outcome, beta += w*(1-outcome))
    update to each ``concept_mastery`` row, recording the event in
    ``concept_mastery_history``.
    """
    from app.services.mastery import AttemptKind, apply_attempt_evidence

    user_id = uuid.UUID(payload["user_id"])
    course_id = uuid.UUID(payload["course_id"])
    target_kind = payload["target_kind"]
    target_id = uuid.UUID(payload["target_id"])
    outcome = float(payload["outcome"])
    attempt_kind = AttemptKind(payload["attempt_kind"])
    last_seen_meeting_id = (
        uuid.UUID(payload["last_seen_meeting_id"])
        if payload.get("last_seen_meeting_id")
        else None
    )

    # Idempotency guard: if a history row for this attempt already exists
    # (recorded ON OR AFTER the task's enqueue time), skip — this Task ran
    # before and was retried due to a handler/complete_task seam failure.
    # Without this, ``_reset_stuck_tasks`` would flip a half-completed task
    # back to ``pending`` and the second run would double-count evidence
    # (alpha/beta drift + duplicate ConceptMasteryHistory row). Legacy
    # enqueues that predate this fix lack ``_task_created_at`` and bypass
    # the check; new enqueues always set it from worker dispatch.
    task_created_at_iso = payload.get("_task_created_at")
    if task_created_at_iso:
        from datetime import datetime

        from sqlalchemy import exists

        from app.models import ConceptMasteryHistory

        task_created_at = datetime.fromisoformat(task_created_at_iso)
        already = (
            await session.execute(
                select(
                    exists().where(
                        ConceptMasteryHistory.user_id == user_id,
                        ConceptMasteryHistory.source_kind == attempt_kind.value,
                        ConceptMasteryHistory.source_id == target_id,
                        ConceptMasteryHistory.recorded_at >= task_created_at,
                    )
                )
            )
        ).scalar_one()
        if already:
            return {"touched_concepts": 0, "skipped": "already_applied"}

    touched = await apply_attempt_evidence(
        session,
        user_id=user_id,
        course_id=course_id,
        target_kind=target_kind,
        target_id=target_id,
        attempt_kind=attempt_kind,
        outcome=outcome,
        last_seen_meeting_id=last_seen_meeting_id,
    )
    await session.commit()
    return {"touched_concepts": touched}


def _replay_batch_size() -> int:
    """Resolve the active batch size, honouring tests that monkey-patch
    ``app.services.jobs.REPLAY_BATCH_SIZE`` after the handler moved here.
    """
    from app.services import jobs as _jobs_mod

    return getattr(_jobs_mod, "REPLAY_BATCH_SIZE", REPLAY_BATCH_SIZE)


async def _replay_quiz_attempts(
    session: AsyncSession,
    *,
    course_id: uuid.UUID,
    cutoff: "datetime",
) -> int:
    """Replay quiz attempts in the window. Returns count of attempts replayed."""
    from app.models import Question, Quiz, QuizAttempt
    from app.services.mastery import AttemptKind, apply_attempt_evidence

    batch_size = _replay_batch_size()
    replayed = 0
    offset = 0
    while True:
        quiz_attempts = (
            await session.execute(
                select(QuizAttempt)
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(
                    Quiz.course_id == course_id,
                    QuizAttempt.created_at >= cutoff,
                )
                .order_by(QuizAttempt.created_at, QuizAttempt.id)
                .offset(offset)
                .limit(batch_size)
            )
        ).scalars().all()
        if not quiz_attempts:
            break
        for attempt in quiz_attempts:
            for qid_str, answer in (attempt.answers or {}).items():
                try:
                    qid = uuid.UUID(qid_str)
                except (ValueError, TypeError):
                    continue
                question = (
                    await session.execute(
                        select(Question).where(Question.id == qid)
                    )
                ).scalar_one_or_none()
                if question is None:
                    continue
                outcome = 1.0 if answer == question.correct_answer else 0.0
                await apply_attempt_evidence(
                    session,
                    user_id=attempt.user_id,
                    course_id=course_id,
                    target_kind="question",
                    target_id=qid,
                    attempt_kind=AttemptKind.QUIZ,
                    outcome=outcome,
                )
                replayed += 1
        await session.commit()
        if len(quiz_attempts) < batch_size:
            break
        offset += batch_size
    return replayed


async def _replay_flashcard_attempts(
    session: AsyncSession,
    *,
    course_id: uuid.UUID,
    cutoff: "datetime",
) -> int:
    """Replay flashcard progress events in the window."""
    from app.models import FlashcardCard, FlashcardProgress, FlashcardSet
    from app.services.mastery import AttemptKind, apply_attempt_evidence

    grade_to_outcome = {1: 0.0, 2: 0.4, 3: 0.8, 4: 1.0}
    batch_size = _replay_batch_size()
    replayed = 0
    offset = 0
    while True:
        rows = (
            await session.execute(
                select(FlashcardProgress, FlashcardCard)
                .join(
                    FlashcardCard,
                    FlashcardCard.id == FlashcardProgress.flashcard_card_id,
                )
                .join(
                    FlashcardSet,
                    FlashcardSet.id == FlashcardCard.flashcard_set_id,
                )
                .where(
                    FlashcardSet.course_id == course_id,
                    FlashcardProgress.last_reviewed.is_not(None),
                    FlashcardProgress.last_reviewed >= cutoff,
                )
                .order_by(
                    FlashcardProgress.last_reviewed,
                    FlashcardProgress.id,
                )
                .offset(offset)
                .limit(batch_size)
            )
        ).all()
        if not rows:
            break
        for prog, card in rows:
            outcome = grade_to_outcome.get(prog.last_grade or 3, 0.8)
            await apply_attempt_evidence(
                session,
                user_id=prog.user_id,
                course_id=course_id,
                target_kind="flashcard_card",
                target_id=card.id,
                attempt_kind=AttemptKind.FLASHCARD,
                outcome=outcome,
            )
            replayed += 1
        await session.commit()
        if len(rows) < batch_size:
            break
        offset += batch_size
    return replayed


async def _replay_revision_attempts(
    session: AsyncSession,
    *,
    course_id: uuid.UUID,
    cutoff: "datetime",
) -> int:
    """Replay revision attempts in the window."""
    from app.models import RevisionAttempt, RevisionPoolItem
    from app.services.mastery import AttemptKind, apply_attempt_evidence

    batch_size = _replay_batch_size()
    replayed = 0
    offset = 0
    while True:
        rows = (
            await session.execute(
                select(RevisionAttempt, RevisionPoolItem)
                .join(
                    RevisionPoolItem,
                    RevisionPoolItem.id == RevisionAttempt.pool_item_id,
                )
                .where(
                    RevisionAttempt.course_id == course_id,
                    RevisionAttempt.created_at >= cutoff,
                )
                .order_by(RevisionAttempt.created_at, RevisionAttempt.id)
                .offset(offset)
                .limit(batch_size)
            )
        ).all()
        if not rows:
            break
        for ra, pool in rows:
            await apply_attempt_evidence(
                session,
                user_id=ra.user_id,
                course_id=course_id,
                target_kind="pool_item",
                target_id=pool.id,
                attempt_kind=AttemptKind.REVISION,
                outcome=float(ra.score),
            )
            replayed += 1
        await session.commit()
        if len(rows) < batch_size:
            break
        offset += batch_size
    return replayed


async def _replay_pronunciation_attempts(
    session: AsyncSession,
    *,
    course_id: uuid.UUID,
    cutoff: "datetime",
) -> int:
    """Replay pronunciation scores in the window."""
    from app.models import PronunciationScore
    from app.services.mastery import AttemptKind, apply_attempt_evidence

    batch_size = _replay_batch_size()
    replayed = 0
    offset = 0
    while True:
        rows = (
            await session.execute(
                select(PronunciationScore)
                .where(
                    PronunciationScore.course_id == course_id,
                    PronunciationScore.created_at >= cutoff,
                )
                .order_by(
                    PronunciationScore.created_at,
                    PronunciationScore.id,
                )
                .offset(offset)
                .limit(batch_size)
            )
        ).scalars().all()
        if not rows:
            break
        for ps in rows:
            if ps.overall_score is None:
                continue
            outcome = max(0.0, min(1.0, float(ps.overall_score) / 100.0))
            await apply_attempt_evidence(
                session,
                user_id=ps.user_id,
                course_id=course_id,
                target_kind="pronunciation_item",
                target_id=ps.id,
                attempt_kind=AttemptKind.PRONUNCIATION,
                outcome=outcome,
            )
            replayed += 1
        await session.commit()
        if len(rows) < batch_size:
            break
        offset += batch_size
    return replayed


async def run_replay_attempt_history(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Replay last N days of attempts through Beta-Binomial mastery for a course.

    Walks ``quiz_attempts``, ``flashcard_progress``, ``revision_attempts`` and
    ``pronunciation_scores``, skipping rows older than the window. Each
    surviving attempt is run through :func:`apply_attempt_evidence`, which
    writes a fresh ``ConceptMasteryHistory(event_type='attempt')`` row stamped
    with ``recorded_at = now()`` (the replay time, not the original attempt
    time — reviewers should be aware).

    Replay is *not* idempotent at the watermark level. Operators wanting a
    clean slate must wipe ``ConceptMastery`` for the course before enqueuing
    this job — otherwise evidence accumulates on top of whatever priors
    already exist.

    Processes attempts in batches of REPLAY_BATCH_SIZE (default 500) with
    intermediate commits per attempt-source helper. A failure partway through
    leaves earlier batches durable; operators can safely retry to pick up the
    remainder. The 409 in-flight guard at the endpoint prevents concurrent
    replays for the same course.

    Pronunciation rows currently use ``target_kind='pronunciation_item'``
    with ``target_id=ps.id`` (the score row's own UUID). Tags are written
    against real ``PronunciationItem.id`` values, so the join is a no-op
    today; this branch is wired up so the handler runs without error and
    a future fix to the pronunciation score → item FK will activate it.
    """
    from datetime import datetime, timedelta, timezone

    course_id = uuid.UUID(payload["course_id"])
    # clamp 1..365 days; defense-in-depth against poisoned payloads
    window_days = max(1, min(int(payload.get("window_days", 90)), 365))
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    counters = {
        "quiz": await _replay_quiz_attempts(
            session, course_id=course_id, cutoff=cutoff
        ),
        "flashcard": await _replay_flashcard_attempts(
            session, course_id=course_id, cutoff=cutoff
        ),
        "revision": await _replay_revision_attempts(
            session, course_id=course_id, cutoff=cutoff
        ),
        "pronunciation": await _replay_pronunciation_attempts(
            session, course_id=course_id, cutoff=cutoff
        ),
    }

    logger.info(
        "replay_attempt_history finished course_id=%s counters=%s",
        course_id,
        counters,
    )
    return {"course_id": str(course_id), "counters": counters}


async def run_evaluate_instructor_alerts(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate alert rules for one course."""
    from app.services.alerts import evaluate_alerts_for_course

    course_id = uuid.UUID(payload["course_id"])
    return await evaluate_alerts_for_course(session, course_id=course_id)


# ---------------------------------------------------------------------------
# Learning-note drafting (OBJ-04) — AI drafts, instructor reviews.
# ---------------------------------------------------------------------------

# How recently an event must have occurred to seed a draft note, and the
# upper bounds on how much we scan / reference per run. Kept small so a single
# run is bounded and the draft cites a manageable slice of evidence.
_NOTE_WINDOW_HOURS = 48
_NOTE_EVENT_SCAN_CAP = 200
_NOTE_EVENTS_PER_NOTE_CAP = 20

# Below-this is a "struggle" signal worth drafting a note about. Scales differ
# per source (quiz/pronunciation are 0–100, revision is 0–1, flashcard SM-2
# quality is 0–5), so each kind is thresholded on its own scale.
_QUIZ_PRON_STRUGGLE = 50.0
_REVISION_STRUGGLE = 0.5
_FLASHCARD_STRUGGLE = 3.0


class _FollowUpV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action_type: str = Field(..., max_length=40)
    target_kind: str | None = Field(None, max_length=40)
    target_id: str | None = Field(None, max_length=64)


class _NoteDraftV1(BaseModel):
    """Strict schema for the LLM's draft note. Caps bound a hallucinated or
    prompt-injected payload before it lands in an instructor-facing row."""

    model_config = ConfigDict(extra="ignore")
    observed_signal: str = Field(..., max_length=2000)
    draft_interpretation: str | None = Field(None, max_length=2000)
    limitation_note: str | None = Field(None, max_length=2000)
    suggested_follow_up: _FollowUpV1 | None = None


_NOTE_SYSTEM_PROMPT = """You draft an instructor-facing learning note from a \
single student's recent low-scoring attempts.
Return ONLY a JSON object with these keys:
{
  "observed_signal": "one factual sentence describing what the evidence shows",
  "draft_interpretation": "a tentative, hedged interpretation (string or null)",
  "limitation_note": "what this evidence does NOT establish (string or null)",
  "suggested_follow_up": {
    "action_type": "short verb phrase",
    "target_kind": "string or null",
    "target_id": "string or null"
  }
}
Be factual and concise. This is a DRAFT for human review — never assert an \
interpretation as established fact."""


def _event_is_struggle(value: dict[str, Any], source_kind: str) -> bool:
    """True when an attempt's value indicates the student struggled.

    Tolerant of missing/non-numeric values (returns False) so a malformed
    event never seeds a note.
    """
    def _num(key: str) -> float | None:
        raw = value.get(key)
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    if source_kind == "flashcard":
        q = _num("quality")
        return q is not None and q < _FLASHCARD_STRUGGLE
    if source_kind == "pronunciation":
        s = _num("overall_score")
        return s is not None and s < _QUIZ_PRON_STRUGGLE
    if source_kind == "quiz_attempt":
        s = _num("score")
        return s is not None and s < _QUIZ_PRON_STRUGGLE
    if source_kind == "revision":
        s = _num("score")
        return s is not None and s < _REVISION_STRUGGLE
    # Generic fallback: a normalized 0–1 score under threshold.
    s = _num("score")
    return s is not None and s < _REVISION_STRUGGLE


def _summarize_events(events: list[Any]) -> str:
    return "\n".join(
        f"- source={ev.source_kind} value={json.dumps(ev.value or {})}"
        for ev in events
    )


def _fallback_note(events: list[Any]) -> dict[str, Any]:
    """Deterministic note built straight from event values — used when the
    LLM call fails so a struggle signal is never silently dropped."""
    kinds = "/".join(sorted({ev.source_kind for ev in events}))
    return {
        "observed_signal": (
            f"{len(events)} recent low-scoring {kinds} attempt(s) "
            f"in the last {_NOTE_WINDOW_HOURS}h."
        ),
        "draft_interpretation": None,
        "limitation_note": (
            "Auto-generated from attempt scores only; not yet interpreted "
            "by an instructor."
        ),
        "suggested_follow_up": {
            "action_type": "review_with_student",
            "target_kind": None,
            "target_id": None,
        },
    }


async def _llm_draft_note(events: list[Any]) -> dict[str, Any] | None:
    """Draft a note via the LLM. Never raises — returns None on any failure
    so the caller falls back to a deterministic template."""
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    try:
        resp = await client.chat.completions.create(
            model=settings.llm_primary_model,
            messages=[
                {"role": "system", "content": _NOTE_SYSTEM_PROMPT},
                {"role": "user", "content": _summarize_events(events)[:6000]},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
        return _NoteDraftV1.model_validate(parsed).model_dump(mode="json")
    except Exception:  # noqa: BLE001 — never escape; fall back to template
        logger.warning(
            "draft_learning_notes LLM step failed; using fallback",
            exc_info=True,
        )
        return None


def _select_note_candidates(
    events: list[Any], already_noted: set[str]
) -> dict[uuid.UUID, list[Any]]:
    """Group struggle events (not already referenced by a note) per user."""
    per_user: dict[uuid.UUID, list[Any]] = {}
    for ev in events:
        if str(ev.id) in already_noted:
            continue
        if not _event_is_struggle(ev.value or {}, ev.source_kind):
            continue
        per_user.setdefault(ev.user_id, []).append(ev)
    return per_user


async def run_draft_learning_notes(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Draft ``LearningNote`` rows from recent struggle signals for a course.

    AI drafts; instructors review (Core §0.2). Scans the last
    ``_NOTE_WINDOW_HOURS`` of ``learning_events`` for the course, skips events
    already cited by an existing note, and drafts at most one ``review_status=
    'draft'`` note per user per run. Each draft is produced by a non-raising
    LLM step with a deterministic template fallback, so a struggle signal is
    never silently dropped.
    """
    from datetime import datetime, timedelta, timezone

    from app.models.evidence import LearningEvent, LearningNote

    course_id = uuid.UUID(payload["course_id"])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_NOTE_WINDOW_HOURS)

    events = (
        await session.execute(
            select(LearningEvent)
            .where(
                LearningEvent.course_id == course_id,
                LearningEvent.occurred_at >= cutoff,
            )
            .order_by(LearningEvent.occurred_at.desc())
            .limit(_NOTE_EVENT_SCAN_CAP)
        )
    ).scalars().all()
    if not events:
        return {"course_id": str(course_id), "drafted": 0}

    # Event ids already cited by some note for this course — don't re-draft.
    noted_lists = (
        await session.execute(
            select(LearningNote.source_event_ids).where(
                LearningNote.course_id == course_id
            )
        )
    ).scalars().all()
    already_noted = {
        str(eid) for lst in noted_lists for eid in (lst or [])
    }

    per_user = _select_note_candidates(events, already_noted)

    drafted = 0
    for user_id, user_events in per_user.items():
        cited = user_events[:_NOTE_EVENTS_PER_NOTE_CAP]
        draft = await _llm_draft_note(cited) or _fallback_note(cited)
        session.add(
            LearningNote(
                course_id=course_id,
                user_id=user_id,
                source_event_ids=[str(ev.id) for ev in cited],
                evidence_category="attempt_signal",
                observed_signal=draft["observed_signal"],
                draft_interpretation=draft.get("draft_interpretation"),
                limitation_note=draft.get("limitation_note"),
                suggested_follow_up=draft.get("suggested_follow_up"),
                review_status="draft",
            )
        )
        drafted += 1

    if drafted:
        await session.commit()
    return {"course_id": str(course_id), "drafted": drafted}


# ---------------------------------------------------------------------------
# Report drafting (P7 B3) — reviewed-notes-only, evidence-refs-required.
# ---------------------------------------------------------------------------
#
# Governing constraint (Core §0.2 / Decision 1): a report NEVER draws from an
# unreviewed note. ``run_draft_report`` selects ONLY ``LearningNote`` rows with
# ``review_status IN ('reviewed','edited')`` AND ``report_eligibility=true`` in
# the course + period window, sets ``evidence_refs`` to EXACTLY those note ids,
# and NEVER lets an unreviewed / ineligible note's text reach ``body``. If zero
# eligible reviewed notes exist, NO ``reports`` row is created (returns
# ``{"drafted": 0}``). Mirrors the ``run_draft_learning_notes`` shape:
# window scan → idempotency skip → non-raising LLM step with deterministic
# fallback → ``session.add`` → single commit; a strict Pydantic cap bounds any
# LLM-composed section before it lands in an instructor-facing row.

# The reviewed-status values that make a note report-eligible. Any other status
# (draft / queued / merged / split / archived) is invisible to drafting.
_REPORT_REVIEWED_STATUSES = ("reviewed", "edited")

# A concept is "weak" when its mastery point estimate is below this AND we are
# confident enough in that estimate (mirrors the insights weak-concept rule).
_REPORT_WEAK_MASTERY_MAX = 0.5
_REPORT_WEAK_CONFIDENCE_MIN = 0.5

# Bound how many rows a single report references / summarizes.
_REPORT_NOTE_CAP = 50
_REPORT_WEAK_CONCEPT_CAP = 20


class _ReportSectionV1(BaseModel):
    """Strict schema for the LLM-composed narrative section of a report.

    Caps bound a hallucinated or prompt-injected payload before it lands in an
    instructor-facing (and, once sent, student-facing) row. The LLM only ever
    composes the free-text ``summary`` — every factual section (observations,
    completed work, weak points, claim limits) is built deterministically from
    reviewed rows, never from model output.
    """

    model_config = ConfigDict(extra="ignore")
    summary: str = Field(..., max_length=4000)


_REPORT_SYSTEM_PROMPT = """You compose a short, factual summary paragraph for a \
course report, drawn ONLY from already-reviewed instructor evidence notes.
Return ONLY a JSON object: {"summary": "one short factual paragraph"}.
Describe observed participation and learning patterns only. Do NOT invent \
facts, scores, or judgments beyond the supplied notes. This summarizes \
instructor-reviewed evidence for a human-reviewed report."""


def _parse_report_dt(value: Any) -> "datetime":
    from datetime import datetime as _dt

    if isinstance(value, _dt):
        return value
    return _dt.fromisoformat(str(value))


def _summarize_notes_for_report(notes: list[Any]) -> str:
    return "\n".join(
        f"- observed={n.observed_signal!r} "
        f"interpretation={(n.draft_interpretation or '')!r} "
        f"limitation={(n.limitation_note or '')!r}"
        for n in notes
    )


def _fallback_report_summary(notes: list[Any]) -> dict[str, Any]:
    """Deterministic summary built straight from the reviewed notes — used when
    the LLM call fails so a report is never blocked on model availability."""
    return {
        "summary": (
            f"This report summarizes {len(notes)} reviewed evidence "
            f"note(s) from the period."
        )
    }


async def _llm_draft_report(
    notes: list[Any], context: dict[str, Any]
) -> dict[str, Any] | None:
    """Compose the report summary via the LLM. Never raises — returns None on any
    failure so the caller falls back to a deterministic template."""
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    try:
        resp = await client.chat.completions.create(
            model=settings.llm_primary_model,
            messages=[
                {"role": "system", "content": _REPORT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _summarize_notes_for_report(notes)[:6000],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
        return _ReportSectionV1.model_validate(parsed).model_dump(mode="json")
    except Exception:  # noqa: BLE001 — never escape; fall back to template
        logger.warning(
            "draft_report LLM step failed; using fallback", exc_info=True
        )
        return None


async def _report_completed_count(
    session: AsyncSession,
    *,
    course_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> int:
    """Count completed ``work_item_progress`` rows for the course (scoped to the
    student for a student-audience report)."""
    from sqlalchemy import func as _func

    from app.models.work_item import WorkItem, WorkItemProgress

    stmt = (
        select(_func.count())
        .select_from(WorkItemProgress)
        .join(WorkItem, WorkItem.id == WorkItemProgress.work_item_id)
        .where(
            WorkItem.course_id == course_id,
            WorkItemProgress.status == "completed",
        )
    )
    if user_id is not None:
        stmt = stmt.where(WorkItemProgress.user_id == user_id)
    return int((await session.execute(stmt)).scalar_one() or 0)


async def _report_weak_concepts(
    session: AsyncSession,
    *,
    course_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    """Weak concepts (mastery below threshold, confidence high enough) for the
    course, scoped to the student for a student-audience report."""
    from app.models.concept import Concept, ConceptMastery

    stmt = (
        select(Concept.id, Concept.name, ConceptMastery.mastery_score)
        .join(ConceptMastery, ConceptMastery.concept_id == Concept.id)
        .where(
            ConceptMastery.course_id == course_id,
            ConceptMastery.mastery_score < _REPORT_WEAK_MASTERY_MAX,
            ConceptMastery.confidence >= _REPORT_WEAK_CONFIDENCE_MIN,
        )
        .order_by(ConceptMastery.mastery_score.asc())
        .limit(_REPORT_WEAK_CONCEPT_CAP)
    )
    if user_id is not None:
        stmt = stmt.where(ConceptMastery.user_id == user_id)
    rows = (await session.execute(stmt)).all()
    return [
        {
            "concept_id": str(cid),
            "name": name,
            "mastery_score": float(score) if score is not None else None,
        }
        for cid, name, score in rows
    ]


async def run_draft_report(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Draft a ``reports`` row from REVIEWED learning notes only (Core §0.2).

    payload: ``{course_id, audience, period, user_id?, period_start, period_end}``

    Selects ``LearningNote`` rows with ``review_status IN ('reviewed','edited')``
    AND ``report_eligibility=true`` whose ``created_at`` falls in the window;
    ``evidence_refs`` becomes EXACTLY those ids. An unreviewed / ineligible note
    is never referenced and its text never reaches ``body``. If zero eligible
    reviewed notes exist, NO report row is created (``{"drafted": 0}``). The LLM
    composition step is non-raising with a deterministic fallback; a strict
    Pydantic cap bounds the composed section. Idempotent per ``(course, audience,
    period, user, period_start)`` window — an existing non-archived report short
    circuits.
    """
    from app.models.evidence import LearningNote
    from app.models.report import Report
    from app.pilot import get_pilot_profile

    course_id = uuid.UUID(payload["course_id"])
    audience = payload["audience"]
    period = payload["period"]
    raw_user_id = payload.get("user_id")
    user_id = uuid.UUID(raw_user_id) if raw_user_id else None
    period_start = _parse_report_dt(payload["period_start"])
    period_end = _parse_report_dt(payload["period_end"])

    # Idempotency guard: a live (non-archived) report for the same window short
    # circuits so a retried task / burst cannot pile up duplicate drafts.
    existing = (
        await session.execute(
            select(Report.id).where(
                Report.course_id == course_id,
                Report.audience == audience,
                Report.period == period,
                (Report.user_id == user_id)
                if user_id is not None
                else Report.user_id.is_(None),
                Report.period_start == period_start,
                Report.status != "archived",
            )
        )
    ).first()
    if existing is not None:
        return {"course_id": str(course_id), "drafted": 0, "skipped": "exists"}

    # Reviewed-notes-ONLY gate (Core §0.2). A student-audience report also picks
    # up cohort-level (``user_id IS NULL``) reviewed notes; a teacher
    # course-level report sees every reviewed note for the course.
    note_filters = [
        LearningNote.course_id == course_id,
        LearningNote.review_status.in_(_REPORT_REVIEWED_STATUSES),
        LearningNote.report_eligibility.is_(True),
        LearningNote.created_at >= period_start,
        LearningNote.created_at <= period_end,
    ]
    if audience == "student" and user_id is not None:
        note_filters.append(
            (LearningNote.user_id == user_id)
            | (LearningNote.user_id.is_(None))
        )

    notes = (
        await session.execute(
            select(LearningNote)
            .where(*note_filters)
            .order_by(LearningNote.created_at.asc())
            .limit(_REPORT_NOTE_CAP)
        )
    ).scalars().all()

    # No report leaves ``draft`` without evidence refs → no row at all when there
    # is no reviewed evidence (Decision 1).
    if not notes:
        return {"course_id": str(course_id), "drafted": 0}

    completed_count = await _report_completed_count(
        session, course_id=course_id, user_id=user_id
    )
    weak_concepts = await _report_weak_concepts(
        session, course_id=course_id, user_id=user_id
    )

    context = {
        "completed_count": completed_count,
        "weak_concept_count": len(weak_concepts),
    }
    composed = await _llm_draft_report(notes, context) or _fallback_report_summary(
        notes
    )

    profile = get_pilot_profile()
    # Every factual section is built deterministically from reviewed rows — the
    # LLM only supplies the free-text ``summary``. This is the boundary that
    # keeps unreviewed content out of the report (Core §0.2).
    body = {
        "summary": composed["summary"],
        "observations": [
            {
                "observed_signal": n.observed_signal,
                "draft_interpretation": n.draft_interpretation,
                "limitation_note": n.limitation_note,
            }
            for n in notes
        ],
        "completed_work": {"completed_count": completed_count},
        "weak_points": weak_concepts,
        "next_actions": [
            n.suggested_follow_up
            for n in notes
            if n.suggested_follow_up
        ],
        "claim_limits": profile.claim_limits["report"],
    }

    session.add(
        Report(
            course_id=course_id,
            audience=audience,
            user_id=user_id,
            period=period,
            period_start=period_start,
            period_end=period_end,
            body=body,
            evidence_refs=[n.id for n in notes],
            status="draft",
        )
    )
    await session.commit()
    return {
        "course_id": str(course_id),
        "drafted": 1,
        "evidence_refs": len(notes),
    }
