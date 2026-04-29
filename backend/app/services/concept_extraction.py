"""LLM concept extraction from a sample of chunks.

Per spec §Concept extraction: send ~200 chunks to the LLM and ask for 5–15
concepts each, returning raw candidates that the clustering step will dedupe.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidateConcept:
    name: str
    description: str | None
    source_chunk_id: uuid.UUID


_SYSTEM_PROMPT = """You extract teachable concepts from educational text.
Return ONLY a JSON array of objects with keys {"name", "description"}.
- "name" is a short canonical phrase (1–6 words), Title Case.
- "description" is a one-sentence explanation (or null).
Output 5–15 concepts. Do not output prose outside the JSON array."""


async def _llm_extract_concepts(text: str) -> list[dict[str, Any]]:
    """Single LLM call. Separate function for monkeypatching in tests."""
    content = text[:8000]   # per-chunk cap; chunks are ~500 tokens but defensive
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    resp = await client.chat.completions.create(
        model=settings.llm_primary_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    raw = resp.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    # Some providers wrap arrays in {"concepts": [...]}; tolerate both.
    if isinstance(parsed, dict):
        items = parsed.get("concepts") or parsed.get("items") or []
        if not items and len(parsed) == 1:
            (only_value,) = parsed.values()
            if isinstance(only_value, list):
                items = only_value
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = []
    return [
        {"name": str(it.get("name", "")).strip(), "description": it.get("description")}
        for it in items
        if isinstance(it, dict) and it.get("name")
    ]


async def extract_candidates_from_chunks(
    chunks: list[dict[str, Any]],
) -> list[CandidateConcept]:
    """Run the LLM extractor across each chunk; ignore individual failures.

    Each ``chunk`` dict must have ``id`` (uuid) and ``content`` (str).
    """
    out: list[CandidateConcept] = []
    for chunk in chunks:
        chunk_id = chunk["id"]
        content = chunk.get("content") or ""
        if not content.strip():
            continue
        try:
            items = await _llm_extract_concepts(content)
        except Exception:
            logger.exception("Concept extraction failed for chunk %s", chunk_id)
            continue
        for it in items:
            name = it["name"][:255].strip()
            if not name:
                continue
            out.append(
                CandidateConcept(
                    name=name,
                    description=(it.get("description") or None),
                    source_chunk_id=chunk_id,
                )
            )
    return out


SAMPLE_CAP = 200


async def sample_chunks_for_extraction(
    db, course_id: uuid.UUID, limit: int = SAMPLE_CAP
) -> list[dict[str, Any]]:
    """Pick up to `limit` chunks from a course, biased toward distinct documents."""
    from sqlalchemy import select, func
    from app.models import Chunk

    # ROW_NUMBER per document so the sample isn't dominated by one big PDF.
    subq = (
        select(
            Chunk.id.label("id"),
            Chunk.content.label("content"),
            func.row_number().over(
                partition_by=Chunk.document_id,
                order_by=Chunk.chunk_index,
            ).label("rn"),
        )
        .where(Chunk.course_id == course_id)
        .subquery()
    )
    stmt = (
        select(subq.c.id, subq.c.content)
        .where(subq.c.rn <= 10)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [{"id": r.id, "content": r.content} for r in rows]
