"""``generate_checkpoints`` job (T022): grounded, DRAFT-only checkpoint drafting.

Grounds on the existing retriever + applied syllabus, drafts review-point cards
via the LLM, always appends exactly one fixed ``final_comments`` card, and
enqueues ``tag_artifact_concepts`` for chunk-anchored cards so they inherit
concept tags (weight ×0.7) through the existing tagger. Status stays ``draft`` —
approve/schedule/publish are P3 (Decision 3).

Retrieval note (executor trap 1): ``retriever.hybrid_retrieve`` requires a
precomputed ``query_embedding`` AND opens its own sessions via
``async_session_factory()``, so it can't see a caller's still-open transaction
(and would hit the network for the embedding). The sibling generation jobs in
``services/jobs.py`` instead call ``embed_query`` + ``retrieve_chunks(session,
...)`` against the caller's session — the proven, transaction-visible path we
follow here. The chunk text lives on ``RetrievedChunk.content``.
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
from app.models.checkpoint import Checkpoint, CheckpointCard
from app.models.chunk import Chunk
from app.models.curriculum import CourseMeeting
from app.models.task import Task
from app.services.carry_forward_memory import load_carry_forward_memory
from app.services.embedder import embed_query
from app.services.retriever import RetrievedChunk, retrieve_chunks
from app.services.syllabus_grounding import load_syllabus_grounding

logger = logging.getLogger(__name__)

# CLE default: 3 review-point cards + 1 fixed final card (§4.2). Teacher-editable
# afterward; the count is a starting point, not a hard limit.
DEFAULT_REVIEW_CARDS = 3

# The fixed final card is not removable (§4.2); its prompt is a constant.
FINAL_CARD_PROMPT = "Any final comments or questions about today's session?"

_CARD_SYSTEM_PROMPT = """You draft short self-assessment "review point" prompts \
for a language-class checkpoint. Given session context, return ONLY a JSON \
object {"cards": [{"prompt": "...", "chunk_id": "<id or null>"}]} where each \
prompt asks a student to rate their confidence on one concept just covered. \
Set chunk_id to the id of the supporting source chunk when the context lists \
one, otherwise null. Be concise and concrete."""


class _CardV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt: str = Field(..., max_length=500)
    chunk_id: str | None = None


class _CardsV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cards: list[_CardV1] = Field(default_factory=list)


async def draft_review_cards(*, context: str, n: int) -> list[dict[str, Any]]:
    """LLM step (separate fn for test monkeypatching).

    Non-raising: on any LLM/parse failure returns a deterministic fallback so
    checkpoint generation never hard-fails the worker.
    """
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    try:
        resp = await client.chat.completions.create(
            model=settings.llm_primary_model,
            messages=[
                {"role": "system", "content": _CARD_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Draft {n} cards.\n\n{context[:6000]}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        parsed = _CardsV1.model_validate(json.loads(raw))
        cards = [c.model_dump() for c in parsed.cards if c.prompt.strip()][:n]
        if cards:
            return cards
    except Exception:  # noqa: BLE001 — never escape; fall back to template
        logger.warning(
            "draft_review_cards LLM step failed; using fallback", exc_info=True
        )
    return [
        {"prompt": "Rate your confidence with today's key point.", "chunk_id": None}
        for _ in range(max(1, n))
    ]


async def retrieve_grounding_chunks(
    db: AsyncSession,
    course_id: uuid.UUID,
    query: str,
    document_ids: list[uuid.UUID] | None = None,
) -> list[RetrievedChunk]:
    """Embed the query and pull the top course chunks against the caller's
    session (mirrors ``services/jobs.py`` grounding). Separated out so tests can
    monkeypatch it and keep generation offline."""
    query_embedding = await embed_query(query)
    return await retrieve_chunks(
        db,
        course_id=course_id,
        query_embedding=query_embedding,
        top_k=6,
        document_ids=document_ids,
    )


def _render_chunks(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks with their ids so the LLM can cite an anchor."""
    return "\n\n".join(
        f"[chunk_id={c.chunk_id}] {c.content[:800]}" for c in chunks
    )


async def _build_context(
    db: AsyncSession, course_id: uuid.UUID, meeting: CourseMeeting
) -> str:
    parts: list[str] = []
    grounding = await load_syllabus_grounding(db, course_id)
    if grounding:
        parts.append(grounding)
    # Prior-term carry-forward memory (T023, Decision 6). Best-effort: a missing
    # or empty import must never break generation. Course-bound — the block holds
    # ONLY instructor summaries, never a student ``user_id``.
    try:
        memory_block = await load_carry_forward_memory(db, course_id)
    except Exception:  # noqa: BLE001 — grounding is best-effort
        logger.warning(
            "load_carry_forward_memory failed during checkpoint gen", exc_info=True
        )
        memory_block = None
    if memory_block:
        parts.append(memory_block)
    if meeting.topic_summary:
        parts.append(f"Session topic: {meeting.topic_summary}")
    query = meeting.topic_summary or meeting.title or "session review"
    try:
        chunks = await retrieve_grounding_chunks(db, course_id, query)
    except Exception:  # noqa: BLE001 — grounding is best-effort
        logger.warning(
            "retrieve_grounding_chunks failed during checkpoint gen", exc_info=True
        )
        chunks = []
    if chunks:
        parts.append(_render_chunks(chunks))
    return "\n\n".join(p for p in parts if p)


async def _resolve_anchor(
    db: AsyncSession, course_id: uuid.UUID, chunk_id_raw: Any
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Validate a card's proposed ``chunk_id`` against a real, in-course chunk.

    Returns ``(chunk_id, document_id)`` when the chunk exists and belongs to the
    course, else ``(None, None)`` — never trust the LLM's id (avoids FK
    violations and cross-course anchoring)."""
    if not chunk_id_raw:
        return None, None
    try:
        chunk_uuid = uuid.UUID(str(chunk_id_raw))
    except (ValueError, TypeError):
        return None, None
    chunk = await db.get(Chunk, chunk_uuid)
    if chunk is None or chunk.course_id != course_id:
        return None, None
    return chunk.id, chunk.document_id


def _checkpoint_title(meeting: CourseMeeting) -> str:
    base = meeting.title or f"Session {meeting.meeting_index}"
    return f"{base} checkpoint"[:255]


async def _generate_for_meeting(
    db: AsyncSession,
    course_id: uuid.UUID,
    meeting: CourseMeeting,
    n_cards: int,
) -> None:
    context = await _build_context(db, course_id, meeting)
    cards = await draft_review_cards(context=context, n=n_cards)

    checkpoint = Checkpoint(
        course_id=course_id,
        meeting_id=meeting.id,
        kind="session",
        title=_checkpoint_title(meeting),
        status="draft",  # Decision 3: DRAFT-only in P1
        generation_meta={
            "source": "generate_checkpoints",
            "meeting_id": str(meeting.id),
        },
    )
    db.add(checkpoint)
    await db.flush()

    position = 0
    for card in cards:
        prompt = (card.get("prompt") or "").strip()
        if not prompt:
            continue
        chunk_uuid, document_uuid = await _resolve_anchor(
            db, course_id, card.get("chunk_id")
        )
        row = CheckpointCard(
            checkpoint_id=checkpoint.id,
            position=position,
            kind="review_point",
            prompt=prompt,
            chunk_id=chunk_uuid,
            document_id=document_uuid,
        )
        db.add(row)
        await db.flush()  # populate row.id before it anchors the tag task
        position += 1
        if chunk_uuid is not None:
            # Reuse the existing inheritance tagger via the worker. Trap 2:
            # target_id is the CARD id, so tags land on the card (not the
            # checkpoint), inheriting the source chunk's tags at weight ×0.7.
            db.add(
                Task(
                    task_type="tag_artifact_concepts",
                    payload={
                        "target_kind": "checkpoint_card",
                        "target_id": str(row.id),
                        "course_id": str(course_id),
                        "source_chunk_id": str(chunk_uuid),
                    },
                    status="pending",
                )
            )

    # Fixed, non-removable final card (§4.2). Exactly one per checkpoint —
    # guarded by the partial unique index ``uq_checkpoint_cards_one_final``.
    db.add(
        CheckpointCard(
            checkpoint_id=checkpoint.id,
            position=position,
            kind="final_comments",
            prompt=FINAL_CARD_PROMPT,
        )
    )


async def run_generate_checkpoints(
    db: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Generate one ``draft`` checkpoint per targeted meeting.

    payload: {course_id, [meeting_id], [review_card_count]}. With ``meeting_id``
    a single session is targeted; without it, every non-deleted meeting in the
    course gets one draft checkpoint.
    """
    course_id = uuid.UUID(payload["course_id"])
    meeting_id = (
        uuid.UUID(payload["meeting_id"]) if payload.get("meeting_id") else None
    )
    n_cards = int(payload.get("review_card_count", DEFAULT_REVIEW_CARDS))

    if meeting_id:
        meeting = await db.get(CourseMeeting, meeting_id)
        meetings = (
            [meeting]
            if meeting is not None
            and meeting.course_id == course_id
            and meeting.deleted_at is None
            else []
        )
    else:
        meetings = (
            await db.execute(
                select(CourseMeeting)
                .where(
                    CourseMeeting.course_id == course_id,
                    CourseMeeting.deleted_at.is_(None),
                )
                .order_by(CourseMeeting.meeting_index)
            )
        ).scalars().all()

    created = 0
    for meeting in meetings:
        await _generate_for_meeting(db, course_id, meeting, n_cards)
        created += 1

    await db.commit()
    return {"course_id": str(course_id), "created": created}
