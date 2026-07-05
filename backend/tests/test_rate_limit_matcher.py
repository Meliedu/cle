"""Unit tests for ``rate_limit._is_rate_limited_path``.

The middleware's path matcher is the gatekeeper for which endpoints get
counted against per-user hourly LLM caps. Mis-matching here means either
spurious 429s on cheap routes or — worse — that an LLM-backed endpoint
escapes rate limiting entirely and an instructor can drain the OpenRouter
budget. These tests pin down the exact set of paths that count.
"""
from __future__ import annotations

import uuid

import pytest

from app.middleware.rate_limit import _is_rate_limited_path


def _course_path(suffix: str) -> str:
    """Build a realistic /api/courses/{uuid}/{suffix} path."""
    return f"/api/courses/{uuid.uuid4()}/{suffix}"


@pytest.mark.parametrize(
    "path",
    [
        "/api/rag/query",
        "/api/rag/generate-quiz",
        "/api/rag/generate-summary",
        "/api/rag/generate-flashcards",
        "/api/rag/jobs/abc-123",  # GET poll — gets per-minute bucket downstream
        "/api/speech/generate-prompts",
    ],
)
def test_existing_rate_limited_paths_still_match(path: str) -> None:
    """Phase 1 paths must keep matching after the Phase 2 extension."""
    assert _is_rate_limited_path(path) is True


def test_syllabus_import_still_matches() -> None:
    assert _is_rate_limited_path(_course_path("syllabus/imports")) is True


@pytest.mark.parametrize("suffix", ["concepts/extract", "concepts/replay"])
def test_phase2_concept_endpoints_match(suffix: str) -> None:
    """L-1 fix: extract/replay are LLM-backed instructor jobs and must be
    counted against the per-user hourly cap. Without this the instructor
    cap silently doesn't apply and a single user can fan out concurrent
    extractions across many owned courses."""
    assert _is_rate_limited_path(_course_path(suffix)) is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/courses",
        "/api/courses/abc",
        # CRUD endpoints on /concepts (list/create/update/delete) — these
        # are NOT LLM-backed and should not eat the hourly quota.
        f"/api/courses/{uuid.uuid4()}/concepts",
        f"/api/courses/{uuid.uuid4()}/concepts/{uuid.uuid4()}",
        # Adjacent course sub-resources that don't trigger LLM jobs.
        f"/api/courses/{uuid.uuid4()}/documents",
        f"/api/courses/{uuid.uuid4()}/students",
        f"/api/courses/{uuid.uuid4()}/syllabus",
        # Nothing under /api/auth/ should ever be rate-limited here.
        "/api/auth/session",
        # Public paths.
        "/health",
        "/docs",
    ],
)
def test_unrelated_paths_do_not_match(path: str) -> None:
    """Guard against the regex over-matching. CRUD on /concepts must stay
    free of the LLM cap, otherwise instructors hit 429 listing concepts."""
    assert _is_rate_limited_path(path) is False


@pytest.mark.parametrize(
    "path",
    [
        # Trailing slash — FastAPI usually normalizes but the matcher
        # uses ``$`` so a trailing slash must NOT match. If FastAPI ever
        # forwards the slashed form we want it to bypass rather than
        # match the wrong bucket.
        f"/api/courses/{uuid.uuid4()}/concepts/extract/",
        # Sub-paths under extract/replay don't exist today; if one is
        # ever added it should re-evaluate explicitly rather than be
        # silently swept in.
        f"/api/courses/{uuid.uuid4()}/concepts/extract/preview",
        # course_id segment containing a slash is not a valid course_id;
        # the [^/]+ guard prevents path-traversal-style false positives.
        "/api/courses//concepts/extract",
    ],
)
def test_regex_anchored_strictly(path: str) -> None:
    assert _is_rate_limited_path(path) is False
