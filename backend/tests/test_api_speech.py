"""Basic import and schema tests for the speech API."""

from app.api.speech import grade, pronunciation_history, router
from app.schemas.speech import (
    PronunciationGradeResponse,
    PronunciationHistoryEntry,
    WordScoreResponse,
)


class TestSpeechSchemas:
    def test_word_score_response(self):
        ws = WordScoreResponse(word="hello", accuracy=92.5, error_type=None)
        assert ws.word == "hello"
        assert ws.accuracy == 92.5
        assert ws.error_type is None

    def test_word_score_response_with_error(self):
        ws = WordScoreResponse(
            word="world", accuracy=40.0, error_type="Mispronunciation"
        )
        assert ws.error_type == "Mispronunciation"

    def test_pronunciation_grade_response(self):
        resp = PronunciationGradeResponse(
            id="abc-123",
            overall_score=90.0,
            accuracy_score=91.5,
            fluency_score=88.0,
            completeness_score=100.0,
            prosody_score=85.0,
            word_scores=[
                WordScoreResponse(word="hello", accuracy=95.0),
                WordScoreResponse(word="world", accuracy=88.0, error_type=None),
            ],
            provider="azure",
        )
        assert resp.id == "abc-123"
        assert resp.overall_score == 90.0
        assert len(resp.word_scores) == 2
        assert resp.provider == "azure"

    def test_pronunciation_grade_response_no_prosody(self):
        resp = PronunciationGradeResponse(
            id="def-456",
            overall_score=78.0,
            accuracy_score=80.0,
            fluency_score=76.0,
            completeness_score=100.0,
            prosody_score=None,
            word_scores=[],
            provider="iflytek",
        )
        assert resp.prosody_score is None
        assert resp.word_scores == []

    def test_pronunciation_history_entry(self):
        entry = PronunciationHistoryEntry(
            id="entry-1",
            target_text="hello world",
            overall_score=85.0,
            accuracy_score=86.0,
            fluency_score=84.0,
            created_at="2026-04-09T10:00:00+00:00",
        )
        assert entry.id == "entry-1"
        assert entry.target_text == "hello world"
        assert entry.overall_score == 85.0
        assert entry.created_at == "2026-04-09T10:00:00+00:00"


class TestSpeechRouterRegistered:
    def test_router_has_routes(self):
        assert len(router.routes) > 0

    def test_router_prefix(self):
        assert router.prefix == "/speech"

    def test_router_tags(self):
        assert "speech" in router.tags

    def test_endpoint_functions_exist(self):
        assert callable(grade)
        assert callable(pronunciation_history)
