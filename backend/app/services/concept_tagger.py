"""Concept tagging.

Two paths:
1. inherit_tags_from_chunk(source_chunk_id, target_kind, target_id) — copy tags
   from a chunk to a derived artifact (question/card/etc.) at weight × 0.7.
2. tag_chunk_via_llm(chunk_text, course_concepts) — LLM picks which concepts
   apply, returns weights. Used for chunks themselves (no upstream to inherit).
"""
from __future__ import annotations

import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Concept, ConceptTag

logger = logging.getLogger(__name__)

INHERITANCE_WEIGHT_FACTOR = Decimal("0.7")


async def inherit_tags_from_chunk(
    db: AsyncSession,
    *,
    source_chunk_id: uuid.UUID,
    target_kind: str,
    target_id: uuid.UUID,
) -> int:
    """Copy chunk's concept tags to a derived target with weight × 0.7."""
    rows = (
        await db.execute(
            select(ConceptTag).where(
                ConceptTag.target_kind == "chunk",
                ConceptTag.target_id == source_chunk_id,
            )
        )
    ).scalars().all()
    inserted = 0
    for r in rows:
        scaled = (r.weight * INHERITANCE_WEIGHT_FACTOR).quantize(Decimal("0.01"))
        if scaled <= 0:
            continue
        stmt = pg_insert(ConceptTag).values(
            concept_id=r.concept_id,
            target_kind=target_kind,
            target_id=target_id,
            weight=scaled,
        ).on_conflict_do_nothing(
            index_elements=["concept_id", "target_kind", "target_id"]
        )
        await db.execute(stmt)
        inserted += 1
    return inserted


_TAGGER_SYSTEM_PROMPT = """You are a tagging engine.
Given a passage and a list of approved course concepts, return ONLY a JSON
array of {"concept_id", "weight"} for the concepts the passage actually
teaches or assesses (omit unrelated concepts).
- weight in [0, 1] reflects how central the concept is to the passage.
- Output an empty array if no concept applies."""


async def _llm_tag_call(text: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Single LLM call. Separate function for monkeypatching in tests."""
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    user_payload = json.dumps({"passage": text[:6000], "concepts": candidates})
    resp = await client.chat.completions.create(
        model=settings.llm_primary_model,
        messages=[
            {"role": "system", "content": _TAGGER_SYSTEM_PROMPT},
            {"role": "user", "content": user_payload},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        items = parsed.get("tags") or parsed.get("items") or []
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = []
    return [it for it in items if isinstance(it, dict) and it.get("concept_id")]


async def tag_chunk_via_llm(
    db: AsyncSession,
    *,
    chunk_id: uuid.UUID,
    chunk_text: str,
    course_id: uuid.UUID,
    max_concepts: int = 5,
) -> int:
    """Tag a chunk using the LLM tagger; insert ``ConceptTag`` rows."""
    approved = (
        await db.execute(
            select(Concept.id, Concept.name, Concept.description).where(
                Concept.course_id == course_id,
                Concept.status == "approved",
                Concept.canonical_id.is_(None),
                Concept.deleted_at.is_(None),
            )
        )
    ).all()
    if not approved:
        return 0
    candidates = [
        {"concept_id": str(c.id), "name": c.name, "description": c.description or ""}
        for c in approved
    ]
    try:
        items = await _llm_tag_call(chunk_text, candidates)
    except Exception:
        logger.exception("LLM tag call failed for chunk %s", chunk_id)
        return 0

    valid_ids = {str(c["concept_id"]) for c in candidates}
    inserted = 0
    for it in items[:max_concepts]:
        cid_str = str(it.get("concept_id", ""))
        if cid_str not in valid_ids:
            continue
        try:
            weight = max(0.0, min(1.0, float(it.get("weight", 1.0))))
        except (TypeError, ValueError):
            continue
        if weight <= 0:
            continue
        stmt = pg_insert(ConceptTag).values(
            concept_id=uuid.UUID(cid_str),
            target_kind="chunk",
            target_id=chunk_id,
            weight=Decimal(f"{weight:.2f}"),
        ).on_conflict_do_nothing(
            index_elements=["concept_id", "target_kind", "target_id"]
        )
        await db.execute(stmt)
        inserted += 1
    return inserted
