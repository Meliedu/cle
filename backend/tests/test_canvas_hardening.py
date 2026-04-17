"""Regression tests for Sprint 8 Canvas hardening.

Covers:
- Task 8.2: validate_canvas_api_url rejects cross-host and non-https
  ``rel="next"`` URLs before the client follows them.
"""

from __future__ import annotations

import pytest

from app.services.url_safety import validate_canvas_api_url


def test_accepts_same_host_https() -> None:
    # Same host + https is the only accepted shape; must not raise.
    validate_canvas_api_url(
        "https://canvas.ust.hk/api/v1/courses/123/pages",
        "https://canvas.ust.hk",
    )


def test_rejects_different_host() -> None:
    with pytest.raises(ValueError, match="host"):
        validate_canvas_api_url(
            "https://evil.example.com/api/v1/foo",
            "https://canvas.ust.hk",
        )


def test_rejects_non_https() -> None:
    with pytest.raises(ValueError, match="https"):
        validate_canvas_api_url(
            "http://canvas.ust.hk/api/v1/foo",
            "https://canvas.ust.hk",
        )


def test_rejects_metadata_endpoint() -> None:
    # Cloud instance metadata endpoints are the canonical SSRF target; the
    # check happens on scheme (http) before host, but either signal must
    # fail the URL.
    with pytest.raises(ValueError):
        validate_canvas_api_url(
            "http://169.254.169.254/latest/meta-data/",
            "https://canvas.ust.hk",
        )
