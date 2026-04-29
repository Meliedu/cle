import uuid

import pytest

from app.services.concept_clustering import cluster_candidates, ConceptCluster
from app.services.concept_extraction import CandidateConcept


def _vec(x):
    """Helper: pad a short vector to 3072 dims."""
    base = list(x)
    return base + [0.0] * (3072 - len(base))


@pytest.mark.asyncio
async def test_cluster_groups_similar_candidates(monkeypatch):
    candidates = [
        CandidateConcept("Big-O Notation", "asymptotic", uuid.uuid4()),
        CandidateConcept("Big O Notation", None, uuid.uuid4()),
        CandidateConcept("Hash Table", None, uuid.uuid4()),
    ]

    async def fake_embed(texts):
        # First two near-identical, third orthogonal.
        return [
            _vec([1.0, 0.0]),
            _vec([0.999, 0.001]),
            _vec([0.0, 1.0]),
        ]

    monkeypatch.setattr(
        "app.services.concept_clustering.embed_concept_texts", fake_embed
    )

    clusters = await cluster_candidates(candidates, threshold=0.15)
    assert len(clusters) == 2
    assert all(isinstance(c, ConceptCluster) for c in clusters)
    big_o_cluster = next(c for c in clusters if "Big" in c.suggested_name)
    assert len(big_o_cluster.members) == 2


@pytest.mark.asyncio
async def test_cluster_empty_returns_empty():
    clusters = await cluster_candidates([], threshold=0.15)
    assert clusters == []
