"""Tests for the speech grading service.

All provider calls are mocked — no real Azure or iFlytek API calls are made.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.speech import (
    PronunciationResult,
    WordScore,
    grade_azure,
    grade_iflytek,
    grade_pronunciation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_azure_mock(
    *,
    assessment: MagicMock,
    recognizer: MagicMock,
) -> MagicMock:
    """Build a complete ``azure.cognitiveservices.speech`` mock module."""
    mock_sdk = MagicMock()
    mock_sdk.SpeechConfig.return_value = MagicMock()
    mock_sdk.PronunciationAssessmentConfig.return_value = MagicMock()
    mock_sdk.PronunciationAssessmentGradingSystem.HundredMark = "HundredMark"
    mock_sdk.PronunciationAssessmentGranularity.Word = "Word"
    mock_sdk.AudioConfig.return_value = MagicMock()
    mock_sdk.SpeechRecognizer.return_value = recognizer
    mock_sdk.PronunciationAssessmentResult.return_value = assessment
    return mock_sdk

# ---------------------------------------------------------------------------
# Dataclass construction
# ---------------------------------------------------------------------------


def test_word_score_construction() -> None:
    ws = WordScore(word="hello", accuracy=92.5, error_type=None)
    assert ws.word == "hello"
    assert ws.accuracy == 92.5
    assert ws.error_type is None


def test_word_score_with_error_type() -> None:
    ws = WordScore(word="world", accuracy=40.0, error_type="Mispronunciation")
    assert ws.error_type == "Mispronunciation"


def test_pronunciation_result_construction() -> None:
    words = [
        WordScore(word="hello", accuracy=95.0),
        WordScore(word="world", accuracy=88.0),
    ]
    result = PronunciationResult(
        overall_score=90.0,
        accuracy_score=91.5,
        fluency_score=88.0,
        completeness_score=100.0,
        prosody_score=85.0,
        word_scores=words,
        provider="azure",
    )
    assert result.overall_score == 90.0
    assert result.accuracy_score == 91.5
    assert result.fluency_score == 88.0
    assert result.completeness_score == 100.0
    assert result.prosody_score == 85.0
    assert len(result.word_scores) == 2
    assert result.provider == "azure"


def test_pronunciation_result_defaults() -> None:
    result = PronunciationResult(
        overall_score=70.0,
        accuracy_score=70.0,
        fluency_score=70.0,
        completeness_score=70.0,
        prosody_score=None,
    )
    assert result.word_scores == []
    assert result.provider == ""


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_english_to_azure() -> None:
    mock_result = PronunciationResult(
        overall_score=85.0,
        accuracy_score=86.0,
        fluency_score=84.0,
        completeness_score=100.0,
        prosody_score=80.0,
        word_scores=[],
        provider="azure",
    )
    with patch(
        "app.services.speech.grade_azure",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_azure:
        result = await grade_pronunciation(b"audio", "hello world", "en")

    mock_azure.assert_awaited_once_with(b"audio", "hello world")
    assert result.provider == "azure"


@pytest.mark.asyncio
async def test_routes_en_us_to_azure() -> None:
    mock_result = PronunciationResult(
        overall_score=85.0,
        accuracy_score=86.0,
        fluency_score=84.0,
        completeness_score=100.0,
        prosody_score=80.0,
        word_scores=[],
        provider="azure",
    )
    with patch(
        "app.services.speech.grade_azure",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await grade_pronunciation(b"audio", "hello world", "en-US")

    assert result.provider == "azure"


@pytest.mark.asyncio
async def test_routes_chinese_to_iflytek() -> None:
    mock_result = PronunciationResult(
        overall_score=78.0,
        accuracy_score=80.0,
        fluency_score=76.0,
        completeness_score=100.0,
        prosody_score=None,
        word_scores=[],
        provider="iflytek",
    )
    with patch(
        "app.services.speech.grade_iflytek",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_iflytek:
        result = await grade_pronunciation(b"audio", "你好世界", "zh")

    mock_iflytek.assert_awaited_once_with(b"audio", "你好世界")
    assert result.provider == "iflytek"


@pytest.mark.asyncio
async def test_routes_zh_cn_to_iflytek() -> None:
    mock_result = PronunciationResult(
        overall_score=78.0,
        accuracy_score=80.0,
        fluency_score=76.0,
        completeness_score=100.0,
        prosody_score=None,
        word_scores=[],
        provider="iflytek",
    )
    with patch(
        "app.services.speech.grade_iflytek",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await grade_pronunciation(b"audio", "你好世界", "zh-CN")

    assert result.provider == "iflytek"


@pytest.mark.asyncio
async def test_routes_chinese_string_to_iflytek() -> None:
    mock_result = PronunciationResult(
        overall_score=78.0,
        accuracy_score=80.0,
        fluency_score=76.0,
        completeness_score=100.0,
        prosody_score=None,
        word_scores=[],
        provider="iflytek",
    )
    with patch(
        "app.services.speech.grade_iflytek",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await grade_pronunciation(b"audio", "你好", "chinese")

    assert result.provider == "iflytek"


# ---------------------------------------------------------------------------
# Mocked Azure provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grade_azure_returns_expected_shape() -> None:
    """Mock the Azure Speech SDK to verify ``grade_azure`` wiring."""
    mock_word = MagicMock()
    mock_word.word = "hello"
    mock_word.accuracy_score = 95.0
    mock_word.error_type = None

    mock_assessment = MagicMock()
    mock_assessment.pronunciation_score = 92.0
    mock_assessment.accuracy_score = 93.0
    mock_assessment.fluency_score = 90.0
    mock_assessment.completeness_score = 100.0
    mock_assessment.prosody_score = 88.0
    mock_assessment.words = [mock_word]

    mock_recognizer = MagicMock()
    mock_recognizer.recognize_once.return_value = MagicMock()

    mock_sdk = _build_azure_mock(assessment=mock_assessment, recognizer=mock_recognizer)

    mock_azure = MagicMock()
    mock_azure_cs = MagicMock()
    mock_azure.cognitiveservices = mock_azure_cs
    mock_azure_cs.speech = mock_sdk

    modules_patch = {
        "azure": mock_azure,
        "azure.cognitiveservices": mock_azure_cs,
        "azure.cognitiveservices.speech": mock_sdk,
    }
    with patch.dict(sys.modules, modules_patch):
        result = await grade_azure(b"fake-wav-bytes", "hello")

    assert isinstance(result, PronunciationResult)
    assert result.provider == "azure"
    assert result.overall_score == 92.0
    assert result.accuracy_score == 93.0
    assert result.fluency_score == 90.0
    assert result.completeness_score == 100.0
    assert result.prosody_score == 88.0
    assert len(result.word_scores) == 1
    assert result.word_scores[0].word == "hello"
    assert result.word_scores[0].accuracy == 95.0
    assert result.word_scores[0].error_type is None


@pytest.mark.asyncio
async def test_grade_azure_captures_word_errors() -> None:
    """Verify that word-level error types are captured."""
    mock_word_ok = MagicMock()
    mock_word_ok.word = "the"
    mock_word_ok.accuracy_score = 98.0
    mock_word_ok.error_type = None

    mock_word_bad = MagicMock()
    mock_word_bad.word = "world"
    mock_word_bad.accuracy_score = 35.0
    mock_word_bad.error_type = "Mispronunciation"

    mock_assessment = MagicMock()
    mock_assessment.pronunciation_score = 65.0
    mock_assessment.accuracy_score = 66.5
    mock_assessment.fluency_score = 70.0
    mock_assessment.completeness_score = 100.0
    mock_assessment.prosody_score = 60.0
    mock_assessment.words = [mock_word_ok, mock_word_bad]

    mock_recognizer = MagicMock()
    mock_recognizer.recognize_once.return_value = MagicMock()

    mock_sdk = _build_azure_mock(assessment=mock_assessment, recognizer=mock_recognizer)

    mock_azure = MagicMock()
    mock_azure_cs = MagicMock()
    mock_azure.cognitiveservices = mock_azure_cs
    mock_azure_cs.speech = mock_sdk

    modules_patch = {
        "azure": mock_azure,
        "azure.cognitiveservices": mock_azure_cs,
        "azure.cognitiveservices.speech": mock_sdk,
    }
    with patch.dict(sys.modules, modules_patch):
        result = await grade_azure(b"fake-wav-bytes", "the world")

    assert len(result.word_scores) == 2
    assert result.word_scores[1].error_type == "Mispronunciation"


# ---------------------------------------------------------------------------
# Mocked iFlytek provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grade_iflytek_returns_expected_shape() -> None:
    """Mock httpx to verify ``grade_iflytek`` wiring."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "code": "0",
        "data": {
            "total_score": 82.0,
            "accuracy_score": 84.0,
            "fluency_score": 80.0,
            "integrity_score": 100.0,
        },
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.speech.httpx.AsyncClient", return_value=mock_client):
        result = await grade_iflytek(b"fake-audio", "你好世界")

    assert isinstance(result, PronunciationResult)
    assert result.provider == "iflytek"
    assert result.overall_score == 82.0
    assert result.accuracy_score == 84.0
    assert result.fluency_score == 80.0
    assert result.completeness_score == 100.0
    assert result.prosody_score is None
    assert result.word_scores == []


@pytest.mark.asyncio
async def test_grade_iflytek_handles_empty_data() -> None:
    """When iFlytek returns empty data, scores default to 0."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"code": "0", "data": {}}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.speech.httpx.AsyncClient", return_value=mock_client):
        result = await grade_iflytek(b"fake-audio", "你好")

    assert result.overall_score == 0
    assert result.accuracy_score == 0
    assert result.fluency_score == 0
    assert result.completeness_score == 0
