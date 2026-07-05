"""Cluster candidate concepts by embedding cosine distance.

Greedy single-link clustering (cosine distance < threshold) — cheap, sufficient
at the per-course scale we expect (~hundreds of candidates).
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field

from app.services.concept_extraction import CandidateConcept
from app.services.embedder import embed_concept_texts


@dataclass(frozen=True)
class ConceptCluster:
    cluster_id: uuid.UUID
    suggested_name: str
    suggested_description: str | None
    members: list[CandidateConcept]
    centroid: list[float] = field(default_factory=list)
    # Per-member embedding vectors, parallel to ``members``. Exposed so
    # callers (notably ``run_extract_concept_candidates``) can persist
    # ``Concept.embedding`` without re-embedding the candidate text.
    member_vectors: list[list[float]] = field(default_factory=list)


def _cos_dist(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return 1.0 - dot / (na * nb)


def _centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(len(vectors[0]))]


def _pick_canonical_name(members: list[CandidateConcept]) -> tuple[str, str | None]:
    # Pick the longest name as canonical (proxies for "most specific"); merge
    # descriptions by picking the first non-null.
    sorted_members = sorted(members, key=lambda c: -len(c.name))
    name = sorted_members[0].name
    description = next((m.description for m in members if m.description), None)
    return name, description


async def cluster_candidates(
    candidates: list[CandidateConcept],
    threshold: float = 0.15,
) -> list[ConceptCluster]:
    if not candidates:
        return []

    texts = [
        f"{c.name}\n{c.description or ''}".strip() for c in candidates
    ]
    embeddings = await embed_concept_texts(texts)

    clusters: list[dict] = []   # each: {"vec": centroid, "members": [...], "vecs": [...]}
    for cand, vec in zip(candidates, embeddings):
        placed = False
        for cl in clusters:
            if _cos_dist(vec, cl["vec"]) < threshold:
                cl["members"].append(cand)
                cl["vecs"].append(vec)
                cl["vec"] = _centroid(cl["vecs"])
                placed = True
                break
        if not placed:
            clusters.append({"vec": vec, "members": [cand], "vecs": [vec]})

    out: list[ConceptCluster] = []
    for cl in clusters:
        name, description = _pick_canonical_name(cl["members"])
        out.append(
            ConceptCluster(
                cluster_id=uuid.uuid4(),
                suggested_name=name,
                suggested_description=description,
                members=list(cl["members"]),
                centroid=cl["vec"],
                member_vectors=list(cl["vecs"]),
            )
        )
    return out
