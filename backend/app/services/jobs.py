"""Async generation jobs.

These handlers encapsulate the work previously performed synchronously inside
``app.api.rag``. They are invoked by ``worker.py`` after a user enqueues a
task via ``POST /rag/generate-*`` and return a small ``result`` dict that the
worker writes back into ``Task.payload["result"]`` so the HTTP polling
endpoint can surface it to the frontend.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.flashcard import FlashcardCard, FlashcardSet, FlashcardSetDocument
from app.models.pronunciation import (
    PronunciationItem,
    PronunciationSet,
    PronunciationSetDocument,
)
from app.models.quiz import Question, Quiz, QuizDocument
from app.models.summary import CourseSummary
from app.models.task import Task
from app.schemas.rag import (
    GenerateFlashcardsRequest,
    GeneratePronunciationRequest,
    GenerateQuizRequest,
    GenerateSummaryRequest,
)
from app.services.embedder import embed_query
from app.services.generator import (
    generate_flashcards,
    generate_pronunciation,
    generate_quiz,
    generate_summary,
)
from app.services.retriever import retrieve_chunks
from app.services.syllabus_grounding import load_syllabus_grounding
from app.utils.sanitize import sanitize_query as _sanitize

logger = logging.getLogger(__name__)


async def _course_language(session: AsyncSession, course_id: uuid.UUID) -> str:
    row = await session.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = row.scalar_one_or_none()
    if course is None:
        raise ValueError(f"Course {course_id} not found")
    return course.language


def _enqueue_artifact_tag_task(
    session: AsyncSession,
    *,
    target_kind: str,
    target_id: uuid.UUID,
    course_id: uuid.UUID,
    source_chunk_id: uuid.UUID | None,
) -> None:
    """Queue a ``tag_artifact_concepts`` job for a freshly-created artifact.

    The downstream handler (``run_tag_artifact_concepts``) inherits chunk
    tags onto the new target at weight × 0.7 via
    ``inherit_tags_from_chunk``. Without ``source_chunk_id`` the inherit
    path has nothing to copy from — skip the enqueue entirely so the
    worker doesn't churn on no-op ``skipped_orphan`` results.

    The Task row is added to the *same* session as the artifact insert.
    The worker commits both together (see ``worker.process_task``), so we
    don't open a separate transaction here and never roll back the
    parent's work.
    """
    if source_chunk_id is None:
        return
    session.add(
        Task(
            task_type="tag_artifact_concepts",
            payload={
                "target_kind": target_kind,
                "target_id": str(target_id),
                "course_id": str(course_id),
                "source_chunk_id": str(source_chunk_id),
            },
            status="pending",
        )
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def run_generate_quiz(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    # Re-validate payload via the same Pydantic schema used at the HTTP edge so
    # that constraints (bounds on num_questions/mcq_option_count, literal sets
    # for purpose/difficulty/question_types) hold even if the payload was
    # tampered with between enqueue and dequeue.
    validated = GenerateQuizRequest.model_validate(
        {
            "course_id": payload["course_id"],
            "title": payload["title"],
            "document_ids": payload.get("document_ids"),
            "num_questions": payload.get("num_questions", 5),
            "purpose": payload.get("purpose", "after_class"),
            # Schema guarantees min_length=1 with a default; the .get() default
            # is belt-and-suspenders only.
            "question_types": payload.get("question_types", ["multiple_choice"]),
            "mcq_option_count": payload.get("mcq_option_count", 4),
            "difficulty": payload.get("difficulty", "medium"),
        }
    )
    course_id = validated.course_id
    user_id = uuid.UUID(payload["user_id"])
    title = validated.title
    num_questions = validated.num_questions
    document_uuids = list(validated.document_ids) if validated.document_ids else None
    purpose = validated.purpose
    question_types = list(validated.question_types)
    mcq_option_count = validated.mcq_option_count
    difficulty = validated.difficulty

    language = await _course_language(session, course_id)
    safe_title = _sanitize(title)

    query_embedding = await embed_query(safe_title)
    chunks = await retrieve_chunks(
        session,
        course_id=course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=document_uuids,
    )
    grounding = await load_syllabus_grounding(session, course_id)
    generated = await generate_quiz(
        chunks,
        num_questions=num_questions,
        language=language,
        question_types=question_types,
        mcq_option_count=mcq_option_count,
        difficulty=difficulty,
        grounding_context=grounding,
    )

    quiz = Quiz(
        course_id=course_id,
        created_by=user_id,
        title=title,
        quiz_type="multiple_choice",
        purpose=purpose,
        is_published=(purpose == "live"),
    )
    session.add(quiz)
    await session.flush()

    # We don't get per-question provenance back from the LLM, so use the
    # top-ranked retrieved chunk as the "primary source" for tag inheritance.
    # Same heuristic as ``pool.replenish_pool``. The 0.7 inheritance weight
    # in ``inherit_tags_from_chunk`` already discounts the loss of fidelity.
    primary_source_chunk_id = chunks[0].chunk_id if chunks else None

    questions: list[Question] = []
    for idx, gq in enumerate(generated):
        question = Question(
            quiz_id=quiz.id,
            question_index=idx,
            type=gq.type,
            question_text=gq.question_text,
            options=gq.options,
            correct_answer=gq.correct_answer,
            explanation=gq.explanation,
            difficulty=gq.difficulty,
            source_chunk_id=primary_source_chunk_id,
        )
        session.add(question)
        questions.append(question)

    if document_uuids:
        for doc_id in document_uuids:
            session.add(QuizDocument(quiz_id=quiz.id, document_id=doc_id))

    await session.flush()

    # Cascade-tag each new question by enqueuing a tag-inheritance job. The
    # task rows commit together with the question rows in the worker.
    for question in questions:
        _enqueue_artifact_tag_task(
            session,
            target_kind="question",
            target_id=question.id,
            course_id=course_id,
            source_chunk_id=question.source_chunk_id,
        )

    logger.info("generate_quiz job finished quiz_id=%s questions=%d", quiz.id, len(generated))
    return {"quiz_id": str(quiz.id), "question_count": len(generated)}


async def run_generate_flashcards(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    # Default difficulty to "medium" when missing so tasks enqueued before
    # the difficulty field was added keep flowing through the worker.
    validated = GenerateFlashcardsRequest.model_validate(
        {
            "course_id": payload["course_id"],
            "title": payload["title"],
            "document_ids": payload.get("document_ids"),
            "num_cards": payload.get("num_cards", 10),
            "difficulty": payload.get("difficulty", "medium"),
        }
    )
    course_id = validated.course_id
    user_id = uuid.UUID(payload["user_id"])
    title = validated.title
    num_cards = validated.num_cards
    document_uuids = list(validated.document_ids) if validated.document_ids else None
    difficulty = validated.difficulty

    language = await _course_language(session, course_id)
    safe_title = _sanitize(title)

    query_embedding = await embed_query(safe_title)
    chunks = await retrieve_chunks(
        session,
        course_id=course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=document_uuids,
    )
    grounding = await load_syllabus_grounding(session, course_id)
    generated = await generate_flashcards(
        chunks,
        num_cards=num_cards,
        language=language,
        difficulty=difficulty,
        grounding_context=grounding,
    )

    fc_set = FlashcardSet(
        course_id=course_id,
        created_by=user_id,
        title=title,
        is_published=False,
    )
    session.add(fc_set)
    await session.flush()

    # Use the top-ranked retrieved chunk as the primary source for tag
    # inheritance — see comment in ``run_generate_quiz`` for rationale.
    primary_source_chunk_id = chunks[0].chunk_id if chunks else None

    # Flashcards generated at mixed difficulty are stored as "medium" per-card
    # since the generator doesn't currently emit a per-card difficulty. A
    # specific-difficulty run tags all cards with that difficulty.
    card_difficulty = difficulty if difficulty != "mixed" else "medium"
    cards: list[FlashcardCard] = []
    for idx, gc in enumerate(generated):
        card = FlashcardCard(
            flashcard_set_id=fc_set.id,
            card_index=idx,
            front=gc.front,
            back=gc.back,
            difficulty=card_difficulty,
            source_chunk_id=primary_source_chunk_id,
        )
        session.add(card)
        cards.append(card)

    if document_uuids:
        for doc_id in document_uuids:
            session.add(
                FlashcardSetDocument(flashcard_set_id=fc_set.id, document_id=doc_id)
            )

    await session.flush()

    for card in cards:
        _enqueue_artifact_tag_task(
            session,
            target_kind="flashcard_card",
            target_id=card.id,
            course_id=course_id,
            source_chunk_id=card.source_chunk_id,
        )

    logger.info(
        "generate_flashcards job finished set_id=%s cards=%d", fc_set.id, len(generated)
    )
    return {"flashcard_set_id": str(fc_set.id), "card_count": len(generated)}


async def run_generate_pronunciation(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    validated = GeneratePronunciationRequest.model_validate(
        {
            "course_id": payload["course_id"],
            "title": payload["title"],
            "document_ids": payload.get("document_ids"),
            "num_items": payload.get("num_items", 10),
            "difficulty": payload.get("difficulty", "medium"),
            "item_types": payload.get("item_types", ["word", "phrase"]),
        }
    )
    course_id = validated.course_id
    user_id = uuid.UUID(payload["user_id"])
    title = validated.title
    num_items = validated.num_items
    document_uuids = list(validated.document_ids) if validated.document_ids else None
    difficulty = validated.difficulty
    item_types = list(validated.item_types)

    language = await _course_language(session, course_id)
    safe_title = _sanitize(title)

    query_embedding = await embed_query(safe_title)
    chunks = await retrieve_chunks(
        session,
        course_id=course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=document_uuids,
    )
    grounding = await load_syllabus_grounding(session, course_id)
    generated = await generate_pronunciation(
        chunks,
        num_items=num_items,
        item_types=item_types,
        difficulty=difficulty,
        language=language,
        grounding_context=grounding,
    )

    pron_set = PronunciationSet(
        course_id=course_id,
        created_by=user_id,
        title=title,
        is_published=False,
        difficulty=difficulty if difficulty != "mixed" else "medium",
        language=language,
    )
    session.add(pron_set)
    await session.flush()

    # Top-ranked retrieved chunk as primary source for tag inheritance —
    # see ``run_generate_quiz`` for rationale.
    primary_source_chunk_id = chunks[0].chunk_id if chunks else None

    items: list[PronunciationItem] = []
    for idx, gp in enumerate(generated):
        item = PronunciationItem(
            pronunciation_set_id=pron_set.id,
            item_index=idx,
            text=gp.text,
            phonetic=gp.phonetic,
            translation=gp.translation,
            tips=gp.tips,
            item_type=gp.item_type,
            difficulty=gp.difficulty,
            source_chunk_id=primary_source_chunk_id,
        )
        session.add(item)
        items.append(item)

    if document_uuids:
        for doc_id in document_uuids:
            session.add(
                PronunciationSetDocument(
                    pronunciation_set_id=pron_set.id, document_id=doc_id
                )
            )

    await session.flush()

    for item in items:
        _enqueue_artifact_tag_task(
            session,
            target_kind="pronunciation_item",
            target_id=item.id,
            course_id=course_id,
            source_chunk_id=item.source_chunk_id,
        )

    logger.info(
        "generate_pronunciation job finished set_id=%s items=%d",
        pron_set.id,
        len(generated),
    )
    return {
        "pronunciation_set_id": str(pron_set.id),
        "item_count": len(generated),
    }


async def run_generate_summary(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    validated = GenerateSummaryRequest.model_validate(
        {
            "course_id": payload["course_id"],
            "document_ids": payload.get("document_ids"),
        }
    )
    course_id = validated.course_id
    user_id = uuid.UUID(payload["user_id"])
    document_uuids = list(validated.document_ids) if validated.document_ids else None

    language = await _course_language(session, course_id)

    query_embedding = await embed_query("comprehensive summary of all material")
    chunks = await retrieve_chunks(
        session,
        course_id=course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=document_uuids,
    )
    grounding = await load_syllabus_grounding(session, course_id)
    summary_text = await generate_summary(
        chunks, language=language, grounding_context=grounding
    )

    existing = await session.execute(
        select(CourseSummary).where(CourseSummary.course_id == course_id)
    )
    record = existing.scalar_one_or_none()
    doc_ids_json = [str(d) for d in document_uuids] if document_uuids else None
    if record is None:
        record = CourseSummary(
            course_id=course_id,
            summary_text=summary_text,
            document_ids=doc_ids_json,
            generated_by=user_id,
        )
        session.add(record)
    else:
        record.summary_text = summary_text
        record.document_ids = doc_ids_json
        record.generated_by = user_id

    await session.flush()
    logger.info("generate_summary job finished course_id=%s", course_id)
    return {"course_id": str(course_id), "summary_id": str(record.id)}


async def run_parse_syllabus(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    import asyncio

    from app.models.curriculum import SyllabusImport
    from app.models.document import Document
    from app.services.parser import parse_document
    from app.services.storage import download_file
    from app.services.syllabus import parse_syllabus_text

    import_id = uuid.UUID(payload["syllabus_import_id"])
    document_id = uuid.UUID(payload["document_id"])

    imp = (
        await session.execute(
            select(SyllabusImport).where(SyllabusImport.id == import_id)
        )
    ).scalar_one_or_none()
    if imp is None:
        return {"status": "missing"}

    doc = (
        await session.execute(
            select(Document).where(Document.id == document_id)
        )
    ).scalar_one_or_none()
    if doc is None or doc.kind != "syllabus":
        imp.status = "failed"
        imp.error_message = "syllabus document missing or kind changed"
        await session.commit()
        return {"status": "failed"}

    # Fix 13: defense-in-depth cross-course check
    if doc.course_id != imp.course_id:
        imp.status = "failed"
        imp.error_message = "document course mismatch"
        await session.commit()
        return {"status": "failed"}

    try:
        raw_bytes = await asyncio.to_thread(download_file, doc.r2_key)
        parse_result = await parse_document(raw_bytes, doc.file_type, doc.filename)
        text = parse_result.text
        imp.raw_text = text[:200000]
        payload_json = await parse_syllabus_text(text)
        imp.parsed_payload = payload_json
        imp.status = "parsed"
        await session.commit()
        return {"status": "parsed", "syllabus_import_id": str(imp.id)}
    except Exception as exc:
        # Fix 3: on any error, mark the import as failed so the UI can re-trigger
        logger.exception(
            "run_parse_syllabus failed for import_id=%s: %s", import_id, exc
        )
        try:
            imp.status = "failed"
            imp.error_message = f"{type(exc).__name__}: {str(exc)[:500]}"
            await session.commit()
        except Exception:
            logger.exception(
                "Failed to persist failure status for import_id=%s", import_id
            )
        return {"status": "failed"}


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

    **Failure mode:** This handler runs all attempts in a single transaction.
    If any apply_attempt_evidence call raises (e.g. DB connection drop), the
    entire replay rolls back. Operators should plan for full retries on
    failure rather than partial-state recovery.

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
    window_days = int(payload.get("window_days", 90))
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    counters = {"quiz": 0, "flashcard": 0, "revision": 0, "pronunciation": 0}

    # --- Quiz attempts -----------------------------------------------------
    quiz_attempts = (
        await session.execute(
            select(QuizAttempt)
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .where(
                Quiz.course_id == course_id,
                QuizAttempt.created_at >= cutoff,
            )
        )
    ).scalars().all()
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

    # --- Flashcard progress (last_reviewed inside window) -----------------
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
        )
    ).all()
    grade_to_outcome = {1: 0.0, 2: 0.4, 3: 0.8, 4: 1.0}
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

    # --- Revision attempts ------------------------------------------------
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
        )
    ).all()
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

    # --- Pronunciation scores --------------------------------------------
    pron_rows = (
        await session.execute(
            select(PronunciationScore).where(
                PronunciationScore.course_id == course_id,
                PronunciationScore.created_at >= cutoff,
            )
        )
    ).scalars().all()
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

    # Commit inside the handler for consistency with sibling concept-job
    # handlers (run_update_concept_mastery, run_extract_concept_candidates,
    # run_tag_artifact_concepts). The worker dispatch branch then doesn't
    # commit again; the test suite calls the handler directly and gets a
    # durable result without needing to remember to commit.
    await session.commit()
    logger.info(
        "replay_attempt_history finished course_id=%s counters=%s",
        course_id,
        counters,
    )
    return {"course_id": str(course_id), "counters": counters}


_HANDLERS = {
    "generate_quiz": run_generate_quiz,
    "generate_flashcards": run_generate_flashcards,
    "generate_pronunciation": run_generate_pronunciation,
    "generate_summary": run_generate_summary,
}


async def run_generation_job(
    session: AsyncSession, task_type: str, payload: dict[str, Any]
) -> dict[str, Any]:
    handler = _HANDLERS.get(task_type)
    if handler is None:
        raise ValueError(f"Unknown generation task type: {task_type}")
    return await handler(session, payload)
