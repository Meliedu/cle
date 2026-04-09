"""Speech grading service with Azure Speech and iFlytek providers.

Routes pronunciation assessment to the appropriate provider based on
language: Azure for English (and other non-Chinese languages), iFlytek
for Chinese.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import tempfile
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings


@dataclass(frozen=True)
class WordScore:
    """Per-word pronunciation score."""

    word: str
    accuracy: float  # 0-100
    error_type: str | None = None  # None, "Mispronunciation", "Omission", "Insertion"


@dataclass(frozen=True)
class PronunciationResult:
    """Aggregated pronunciation assessment result."""

    overall_score: float  # 0-100
    accuracy_score: float  # 0-100
    fluency_score: float  # 0-100
    completeness_score: float  # 0-100
    prosody_score: float | None  # 0-100, Azure only
    word_scores: list[WordScore] = field(default_factory=list)
    provider: str = ""


async def grade_azure(audio_bytes: bytes, reference_text: str) -> PronunciationResult:
    """Grade pronunciation using Azure Speech SDK."""
    import azure.cognitiveservices.speech as speechsdk

    speech_config = speechsdk.SpeechConfig(
        subscription=settings.azure_speech_key,
        region=settings.azure_speech_region,
    )
    pronunciation_config = speechsdk.PronunciationAssessmentConfig(
        reference_text=reference_text,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Word,
        enable_prosody_assessment=True,
    )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        audio_config = speechsdk.AudioConfig(filename=temp_path)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
        pronunciation_config.apply_to(recognizer)
        result = recognizer.recognize_once()
        assessment = speechsdk.PronunciationAssessmentResult(result)

        word_scores: list[WordScore] = []
        for word in assessment.words:
            word_scores.append(
                WordScore(
                    word=word.word,
                    accuracy=word.accuracy_score,
                    error_type=getattr(word, "error_type", None),
                )
            )

        return PronunciationResult(
            overall_score=assessment.pronunciation_score,
            accuracy_score=assessment.accuracy_score,
            fluency_score=assessment.fluency_score,
            completeness_score=assessment.completeness_score,
            prosody_score=getattr(assessment, "prosody_score", None),
            word_scores=word_scores,
            provider="azure",
        )
    finally:
        os.unlink(temp_path)


async def grade_iflytek(audio_bytes: bytes, reference_text: str) -> PronunciationResult:
    """Grade pronunciation using iFlytek Speech Evaluation API."""
    ts = str(int(time.time()))
    base_string = f"{settings.iflytek_app_id}{ts}"
    signature = hmac.new(
        settings.iflytek_api_secret.encode(),
        base_string.encode(),
        hashlib.sha256,
    ).digest()
    sig_b64 = base64.b64encode(signature).decode()
    audio_b64 = base64.b64encode(audio_bytes).decode()

    payload = {
        "common": {"app_id": settings.iflytek_app_id},
        "business": {
            "category": "read_sentence",
            "rstcd": "utf8",
            "text": reference_text,
        },
        "data": {"audio": audio_b64},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.xfyun.cn/v1/service/v1/ise",
            json=payload,
            headers={
                "X-Appid": settings.iflytek_app_id,
                "X-CurTime": ts,
                "X-Param": sig_b64,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    result_data = data.get("data", {})
    return PronunciationResult(
        overall_score=result_data.get("total_score", 0),
        accuracy_score=result_data.get("accuracy_score", 0),
        fluency_score=result_data.get("fluency_score", 0),
        completeness_score=result_data.get("integrity_score", 0),
        prosody_score=None,
        word_scores=[],
        provider="iflytek",
    )


async def grade_pronunciation(
    audio_bytes: bytes,
    reference_text: str,
    language: str,
) -> PronunciationResult:
    """Route to appropriate provider based on language.

    Chinese languages go to iFlytek; everything else goes to Azure.
    """
    if language.startswith("zh") or language == "chinese":
        return await grade_iflytek(audio_bytes, reference_text)
    return await grade_azure(audio_bytes, reference_text)
