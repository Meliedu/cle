"""Tests for the VLM caption client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import openai
import pytest

from app.services import vlm


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    vlm._client = None
    yield
    vlm._client = None


def _fake_completion(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


@pytest.mark.asyncio
async def test_caption_image_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(vlm.settings, "enable_figure_captions", False)
    monkeypatch.setattr(vlm.settings, "openrouter_api_key", "test-key")

    result = await vlm.caption_image(b"\x89PNG\r\n\x1a\nfake")
    assert result is None


@pytest.mark.asyncio
async def test_caption_image_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(vlm.settings, "enable_figure_captions", True)
    monkeypatch.setattr(vlm.settings, "openrouter_api_key", "")

    result = await vlm.caption_image(b"\x89PNG\r\n\x1a\nfake")
    assert result is None


@pytest.mark.asyncio
async def test_caption_image_returns_none_on_empty_bytes(monkeypatch):
    monkeypatch.setattr(vlm.settings, "enable_figure_captions", True)
    monkeypatch.setattr(vlm.settings, "openrouter_api_key", "test-key")

    result = await vlm.caption_image(b"")
    assert result is None


@pytest.mark.asyncio
async def test_caption_image_happy_path(monkeypatch):
    monkeypatch.setattr(vlm.settings, "enable_figure_captions", True)
    monkeypatch.setattr(vlm.settings, "openrouter_api_key", "test-key")

    mock_create = AsyncMock(return_value=_fake_completion("A bar chart."))
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
    )
    monkeypatch.setattr(vlm, "_get_client", lambda: fake_client)

    result = await vlm.caption_image(b"\x89PNG\r\n\x1a\nfake", context="slide 3")

    assert result == "A bar chart."
    mock_create.assert_awaited_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["model"] == vlm.settings.vlm_model
    # Image payload should include a data URI.
    content = kwargs["messages"][0]["content"]
    assert any(part.get("type") == "image_url" for part in content)
    image_url = next(part["image_url"]["url"] for part in content if part.get("type") == "image_url")
    assert image_url.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_caption_image_returns_none_on_timeout(monkeypatch):
    """Timeouts must not raise — they return None so the pipeline keeps going."""
    monkeypatch.setattr(vlm.settings, "enable_figure_captions", True)
    monkeypatch.setattr(vlm.settings, "openrouter_api_key", "test-key")

    async def _always_times_out(*_args, **_kwargs):
        raise openai.APITimeoutError(request=None)

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=_always_times_out)
        )
    )
    monkeypatch.setattr(vlm, "_get_client", lambda: fake_client)
    # Make retries instant.
    with patch("app.services.vlm.asyncio.sleep", new=AsyncMock(return_value=None)):
        result = await vlm.caption_image(b"\x89PNG\r\n\x1a\nfake")

    assert result is None


@pytest.mark.asyncio
async def test_caption_image_returns_none_on_unexpected_error(monkeypatch):
    monkeypatch.setattr(vlm.settings, "enable_figure_captions", True)
    monkeypatch.setattr(vlm.settings, "openrouter_api_key", "test-key")

    async def _boom(*_args, **_kwargs):
        raise ValueError("upstream garbage")

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_boom))
    )
    monkeypatch.setattr(vlm, "_get_client", lambda: fake_client)

    result = await vlm.caption_image(b"\x89PNG\r\n\x1a\nfake")
    assert result is None


def test_detect_mime_png():
    assert vlm._detect_mime(b"\x89PNG\r\n\x1a\nrest") == "image/png"


def test_detect_mime_jpeg():
    assert vlm._detect_mime(b"\xff\xd8\xff\xe0rest") == "image/jpeg"


def test_detect_mime_fallback():
    assert vlm._detect_mime(b"unknown-bytes") == "image/png"
