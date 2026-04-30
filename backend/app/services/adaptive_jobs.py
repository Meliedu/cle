"""Adaptive-engine async job handlers.

Concept extraction, concept tagging, mastery updates, attempt-history
replay, next-actions materialisation, action-outcome telemetry, instructor
alerts, and quarterly coefficient retuning live here.

These were extracted from ``app.services.jobs`` to keep that module under
the 800-line cap. ``jobs.py`` re-exports the handlers below for backward
compatibility, so callers that import them from ``app.services.jobs``
continue to work unchanged.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    intermediate commits. A failure partway through leaves earlier batches
    durable; operators can safely retry to pick up the remainder. The 409
    in-flight guard at the endpoint prevents concurrent replays for the same
    course.

    Pronunciation rows currently use ``target_kind='pronunciation_item'``
    with ``target_id=ps.id`` (the score row's own UUID). Tags are written
    against real ``PronunciationItem.id`` values, so the join is a no-op
    today; this branch is wired up so the handler runs without error and
    a future fix to the pronunciation score → item FK will activate it.
    """
    from datetime import datetime, timedelta, timezone

    from app.models import (
        FlashcardCard,
        FlashcardProgress,
        FlashcardSet,
        PronunciationScore,
        Question,
        Quiz,
        QuizAttempt,
        RevisionAttempt,
        RevisionPoolItem,
    )
    from app.services.mastery import AttemptKind, apply_attempt_evidence

    course_id = uuid.UUID(payload["course_id"])
    # clamp 1..365 days; defense-in-depth against poisoned payloads
    window_days = max(1, min(int(payload.get("window_days", 90)), 365))
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    counters = {"quiz": 0, "flashcard": 0, "revision": 0, "pronunciation": 0}
    # Read REPLAY_BATCH_SIZE through ``app.services.jobs`` so existing tests
    # that monkey-patch ``app.services.jobs.REPLAY_BATCH_SIZE`` keep working
    # after the handler moved here. ``jobs`` re-exports ours, so the two
    # stay in sync; if the patch is absent we fall back to our own copy.
    from app.services import jobs as _jobs_mod

    batch_size = getattr(_jobs_mod, "REPLAY_BATCH_SIZE", REPLAY_BATCH_SIZE)

    # --- Quiz attempts -----------------------------------------------------
    quiz_offset = 0
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
                .offset(quiz_offset)
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
                counters["quiz"] += 1
        await session.commit()
        if len(quiz_attempts) < batch_size:
            break
        quiz_offset += batch_size

    # --- Flashcard progress (last_reviewed inside window) -----------------
    grade_to_outcome = {1: 0.0, 2: 0.4, 3: 0.8, 4: 1.0}
    fc_offset = 0
    while True:
        fc_rows = (
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
                .offset(fc_offset)
                .limit(batch_size)
            )
        ).all()
        if not fc_rows:
            break
        for prog, card in fc_rows:
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
            counters["flashcard"] += 1
        await session.commit()
        if len(fc_rows) < batch_size:
            break
        fc_offset += batch_size

    # --- Revision attempts ------------------------------------------------
    rev_offset = 0
    while True:
        rev_rows = (
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
                .offset(rev_offset)
                .limit(batch_size)
            )
        ).all()
        if not rev_rows:
            break
        for ra, pool in rev_rows:
            await apply_attempt_evidence(
                session,
                user_id=ra.user_id,
                course_id=course_id,
                target_kind="pool_item",
                target_id=pool.id,
                attempt_kind=AttemptKind.REVISION,
                outcome=float(ra.score),
            )
            counters["revision"] += 1
        await session.commit()
        if len(rev_rows) < batch_size:
            break
        rev_offset += batch_size

    # --- Pronunciation scores --------------------------------------------
    pron_offset = 0
    while True:
        pron_rows = (
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
                .offset(pron_offset)
                .limit(batch_size)
            )
        ).scalars().all()
        if not pron_rows:
            break
        for ps in pron_rows:
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
            counters["pronunciation"] += 1
        await session.commit()
        if len(pron_rows) < batch_size:
            break
        pron_offset += batch_size

    logger.info(
        "replay_attempt_history finished course_id=%s counters=%s",
        course_id,
        counters,
    )
    return {"course_id": str(course_id), "counters": counters}


async def run_materialize_next_actions(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Materialise top-10 next_actions for one (user, course)."""
    from app.services.next_actions import materialize_next_actions

    user_id = uuid.UUID(payload["user_id"])
    course_id = uuid.UUID(payload["course_id"])
    rows = await materialize_next_actions(
        session, user_id=user_id, course_id=course_id
    )
    return {"count": len(rows), "user_id": str(user_id), "course_id": str(course_id)}


async def run_record_action_outcome(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Persist a single action_outcomes row.

    Used by both the click endpoint (clicked=True) and the post-attempt
    observation hook (completed=True with outcome_metric+outcome_score).
    """
    from datetime import datetime
    from decimal import Decimal

    from app.models import ActionOutcome

    # Bundle every payload-parsing failure into a single descriptive
    # ValueError so a malformed task surfaces a useful ``error_message``
    # rather than a bare KeyError / ValueError from deep inside the
    # constructor.
    try:
        served_at = datetime.fromisoformat(payload["served_at"])
        user_id = uuid.UUID(payload["user_id"])
        action_type = payload["action_type"]
        engine_variant = payload["engine_variant"]
        next_action_id_raw = payload.get("next_action_id")
        next_action_id = (
            uuid.UUID(next_action_id_raw) if next_action_id_raw else None
        )
        course_id_raw = payload.get("course_id")
        course_id = uuid.UUID(course_id_raw) if course_id_raw else None
        target_id_raw = payload.get("target_id")
        target_id = uuid.UUID(target_id_raw) if target_id_raw else None
        outcome_score_raw = payload.get("outcome_score")
        outcome_score = (
            Decimal(f"{float(outcome_score_raw):.3f}")
            if outcome_score_raw is not None else None
        )
        observed_at_raw = payload.get("observed_at")
        observed_at = (
            datetime.fromisoformat(observed_at_raw) if observed_at_raw else None
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(
            f"malformed record_action_outcome payload: {exc}"
        ) from exc

    row = ActionOutcome(
        next_action_id=next_action_id,
        user_id=user_id,
        course_id=course_id,
        action_type=action_type,
        target_kind=payload.get("target_kind"),
        target_id=target_id,
        engine_variant=engine_variant,
        served_at=served_at,
        clicked=bool(payload.get("clicked", False)),
        completed=bool(payload.get("completed", False)),
        outcome_score=outcome_score,
        outcome_metric=payload.get("outcome_metric"),
        observed_at=observed_at,
    )
    session.add(row)
    await session.commit()
    return {"status": "recorded", "id": str(row.id)}


async def run_evaluate_instructor_alerts(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate alert rules for one course (Task 15 fills the body)."""
    from app.services.alerts import evaluate_alerts_for_course

    course_id = uuid.UUID(payload["course_id"])
    return await evaluate_alerts_for_course(session, course_id=course_id)


async def run_tune_action_coefficients(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Quarterly coefficient retune (Task 17 fills the body)."""
    from app.services.action_coeffs import retune_action_coefficients

    window_days = int(payload.get("window_days", 90))
    return await retune_action_coefficients(session, window_days=window_days)
