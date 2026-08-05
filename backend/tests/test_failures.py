"""The safe failure contract.

Guards the defect the approved handoff calls out in Plate 05, note 3: the live
product rendered a raw Python exception to an instructor. These tests assert
that the classifier both maps that exception correctly and never returns
anything that could carry internals to the UI.
"""

from __future__ import annotations

import logging

import pytest

from app.services.failures import (
    RETRYABLE_CODES,
    SourceFailureCode,
    classify,
    classify_and_log,
    is_retryable,
)


class TestClassifyByExceptionType:
    def test_the_exact_leaked_exception_is_classified_as_internal(self):
        """`AttributeError: 'Settings' object has no attribute 'llm_primary_model'`

        is a misconfiguration on our side, so it must not be reported as a
        problem with the instructor's file.
        """
        exc = AttributeError(
            "'Settings' object has no attribute 'llm_primary_model'"
        )
        assert classify(exc) is SourceFailureCode.ANALYSIS_UNAVAILABLE

    def test_timeouts_classify_as_timeout(self):
        assert classify(TimeoutError("deadline")) is SourceFailureCode.TIMEOUT

    def test_missing_file_classifies_as_storage(self):
        assert (
            classify(FileNotFoundError("nope"))
            is SourceFailureCode.STORAGE_UNAVAILABLE
        )

    def test_subclasses_resolve_through_the_mro(self):
        class MySettingsError(AttributeError):
            pass

        assert (
            classify(MySettingsError("boom"))
            is SourceFailureCode.ANALYSIS_UNAVAILABLE
        )

    def test_exception_type_wins_over_a_misleading_message(self):
        # The message mentions "parse", but the type says internal defect.
        exc = AttributeError("could not parse settings")
        assert classify(exc) is SourceFailureCode.ANALYSIS_UNAVAILABLE

    def test_a_rejected_provider_key_is_ours_not_the_users_file(self):
        """The 4 Aug 2026 incident: a revoked OpenRouter key on the worker.

        The provider answered ``401 {'message': 'User not found.'}`` on every
        embedding call. No substring in that message names a key, a quota or a
        provider, so it fell through to UNKNOWN, which is retryable, so the UI
        offered a Retry that re-ran download, parse and embed to fail
        identically. A rejected credential is an operator fix.
        """

        class AuthenticationError(Exception):
            """Shape of ``openai.AuthenticationError`` without the SDK import."""

        exc = AuthenticationError(
            "Error code: 401 - {'error': {'message': 'User not found.', "
            "'code': 401}}"
        )
        assert classify(exc) is SourceFailureCode.ANALYSIS_UNAVAILABLE
        assert not is_retryable(classify(exc))

    def test_a_provider_blip_stays_retryable(self):
        """A 429 or a provider 5xx is transient, unlike a rejected key.

        Found in review: both used to land in ANALYSIS_UNAVAILABLE via the
        message table ("rate limit", "openrouter"), and making that code
        non-retryable would have removed the Retry button for failures a second
        attempt would clear. That is the opposite of what keeping the uploaded
        bytes was for.
        """

        class RateLimitError(Exception):
            """Shape of ``openai.RateLimitError`` (429)."""

        class APIConnectionError(Exception):
            """Shape of ``openai.APIConnectionError``."""

        for exc in (
            RateLimitError("Error code: 429 - rate limit exceeded"),
            APIConnectionError("Connection error."),
        ):
            code = classify(exc)
            assert code is SourceFailureCode.PROVIDER_UNAVAILABLE, exc
            assert is_retryable(code), exc

    def test_a_provider_outage_message_is_retryable_too(self):
        """Falls to the message table, which must not bucket it with defects."""
        code = classify(RuntimeError("openrouter returned 503 Service Unavailable"))
        assert code is SourceFailureCode.PROVIDER_UNAVAILABLE
        assert is_retryable(code)

    def test_a_rejected_permission_is_also_ours(self):
        class PermissionDeniedError(Exception):
            """Shape of ``openai.PermissionDeniedError`` (403)."""

        assert (
            classify(PermissionDeniedError("Error code: 403"))
            is SourceFailureCode.ANALYSIS_UNAVAILABLE
        )


class TestClassifyByMessage:
    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            ("Unsupported file type: .key", SourceFailureCode.UNSUPPORTED_FORMAT),
            ("File too large (120 MB)", SourceFailureCode.FILE_TOO_LARGE),
            ("no extractable text found", SourceFailureCode.EMPTY_DOCUMENT),
            ("request timed out after 60s", SourceFailureCode.TIMEOUT),
            # Was ANALYSIS_UNAVAILABLE. A rate limit is the provider declining
            # to serve right now, not a defect in our configuration, and the
            # two need different answers once that code stops offering Retry.
            ("rate limit exceeded", SourceFailureCode.PROVIDER_UNAVAILABLE),
            ("model is overloaded, try again", SourceFailureCode.PROVIDER_UNAVAILABLE),
            ("invalid api key supplied", SourceFailureCode.ANALYSIS_UNAVAILABLE),
            ("NoSuchKey when reading object", SourceFailureCode.STORAGE_UNAVAILABLE),
            ("could not parse PDF, file is corrupt", SourceFailureCode.UNREADABLE_FILE),
        ],
    )
    def test_message_substrings(self, message, expected):
        assert classify(RuntimeError(message)) is expected

    def test_unrecognised_failure_falls_back_to_unknown(self):
        assert classify(RuntimeError("something odd")) is SourceFailureCode.UNKNOWN


class TestRetryability:
    def test_transient_failures_are_retryable(self):
        for code in (
            SourceFailureCode.TIMEOUT,
            SourceFailureCode.STORAGE_UNAVAILABLE,
            SourceFailureCode.UNREADABLE_FILE,
            SourceFailureCode.UNKNOWN,
        ):
            assert is_retryable(code), code

    def test_failures_needing_a_different_file_are_not_retryable(self):
        for code in (
            SourceFailureCode.UNSUPPORTED_FORMAT,
            SourceFailureCode.FILE_TOO_LARGE,
            SourceFailureCode.EMPTY_DOCUMENT,
        ):
            assert not is_retryable(code), code

    def test_our_own_defects_are_not_offered_as_retryable(self):
        """ANALYSIS_UNAVAILABLE is the bucket for AttributeError / KeyError /
        ImportError: our bugs and misconfiguration. A retry re-runs download,
        parse and embedding at real cost only to fail identically, so the UI
        must not invite the instructor to keep clicking."""
        assert not is_retryable(SourceFailureCode.ANALYSIS_UNAVAILABLE)

    def test_every_code_has_a_defined_retryability(self):
        for code in SourceFailureCode:
            # Membership is total: no code is silently absent from the set.
            assert isinstance(is_retryable(code), bool)
            assert (code in RETRYABLE_CODES) == is_retryable(code)


class TestClassifyAndLog:
    def test_returns_only_a_code_never_the_exception_text(self):
        exc = AttributeError(
            "'Settings' object has no attribute 'llm_primary_model'"
        )
        code = classify_and_log(exc, context="run_parse_syllabus", import_id="i1")

        assert isinstance(code, SourceFailureCode)
        # The value is a short enum token, not a message.
        assert code.value == "analysis_unavailable"
        assert "Settings" not in code.value
        assert "llm_primary_model" not in code.value

    def test_raw_detail_still_reaches_the_structured_log(self, caplog):
        """Operators must not lose triage information to the safe UI copy."""
        exc = AttributeError(
            "'Settings' object has no attribute 'llm_primary_model'"
        )
        with caplog.at_level(logging.ERROR, logger="app.services.failures"):
            classify_and_log(
                exc,
                context="run_parse_syllabus",
                import_id="i1",
                course_id="c1",
            )

        record = caplog.records[-1]
        # `assert record.exc_info is not None` alone was vacuous: called
        # outside an except block, logger.exception() records the sentinel
        # (None, None, None), which satisfies "is not None" while carrying no
        # traceback at all. Assert the exception itself is attached.
        assert record.exc_info is not None
        assert record.exc_info[1] is exc, (
            "the exception must be attached explicitly, so a traceback is "
            "captured from any call site, not only from inside an except block"
        )
        text = record.getMessage()
        assert "run_parse_syllabus" in text
        assert "AttributeError" in text
        # Identifiers stay server-side for triage.
        assert "import_id=i1" in text
        assert "course_id=c1" in text

    def test_every_enum_value_is_a_safe_token(self):
        """No code may itself be capable of leaking internals."""
        for code in SourceFailureCode:
            assert code.value.islower()
            assert code.value.replace("_", "").isalpha()
            assert ":" not in code.value
            assert " " not in code.value
