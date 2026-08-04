"""Typed, user-safe failure classification for source processing.

The approved UI/UX handoff (22 July 2026) makes this a release gate:

    Raw exception text, provider operation, object key, stack name, and request
    identifier stay in structured server logs.

    Map backend failures to typed, user-safe errors. Log raw detail
    server-side; announce status changes accessibly.

The live product violated this: an instructor uploading a syllabus was shown

    AttributeError: 'Settings' object has no attribute 'llm_primary_model'

because ``run_parse_syllabus`` stored ``str(exc)`` in ``SyllabusImport.error_message``
and the API returned that column verbatim.

This module replaces that path. ``classify`` maps any exception onto a small
enum whose members the frontend knows how to render (see
``frontend/src/lib/contracts/safe-error.ts``); the raw exception continues to
reach the structured logs untouched, where triage actually needs it.

The enum values are the wire contract. Changing one is a breaking change for
the frontend, which switches on them to select copy.
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class SourceFailureCode(str, Enum):
    """Why a source could not be processed, in terms a user can act on.

    Mirrors ``SafeErrorCode`` on the frontend. Every member must have an entry
    in that module's ``SAFE_COPY`` table; adding one here without adding it
    there leaves the UI with generic copy.
    """

    #: The file was read but its contents could not be parsed.
    UNREADABLE_FILE = "unreadable_file"
    #: The file type is not one the parser supports.
    UNSUPPORTED_FORMAT = "unsupported_format"
    #: The file exceeded the size the pipeline accepts.
    FILE_TOO_LARGE = "file_too_large"
    #: Parsed successfully but yielded no usable text (e.g. a scanned PDF).
    EMPTY_DOCUMENT = "empty_document"
    #: Object storage could not return the file.
    STORAGE_UNAVAILABLE = "storage_unavailable"
    #: The model/analysis step failed or was misconfigured.
    ANALYSIS_UNAVAILABLE = "analysis_unavailable"
    #: The operation exceeded its time budget.
    TIMEOUT = "timeout"
    #: The referenced object vanished or changed identity under us.
    NOT_FOUND = "not_found"
    #: Anything not otherwise classified.
    UNKNOWN = "unknown"


#: Codes whose recovery path is "try again" rather than "replace the file".
#: Codes worth offering a Retry for. The test is "could the same input
#: plausibly succeed on a second attempt", not "did this fail".
#:
#: ANALYSIS_UNAVAILABLE is deliberately EXCLUDED. It is the bucket for
#: AttributeError / KeyError / ImportError, i.e. our own defects and
#: misconfiguration, and a retry re-runs download, parse (Docling plus VLM
#: captioning) and embedding only to fail identically. Offering Retry there
#: spends real money to show the instructor the same failure, and invites them
#: to keep clicking. Recovery is an operator fix, not a user action.
RETRYABLE_CODES = frozenset(
    {
        SourceFailureCode.UNREADABLE_FILE,
        SourceFailureCode.STORAGE_UNAVAILABLE,
        SourceFailureCode.TIMEOUT,
        SourceFailureCode.UNKNOWN,
    }
)


def is_retryable(code: SourceFailureCode) -> bool:
    """Whether the UI should offer a Retry affordance for ``code``."""
    return code in RETRYABLE_CODES


# Exception type names that reliably indicate a specific failure mode. Matched
# on the class name rather than by importing every provider SDK, so this module
# stays free of optional third-party imports.
_BY_EXCEPTION_NAME: dict[str, SourceFailureCode] = {
    "TimeoutError": SourceFailureCode.TIMEOUT,
    "AsyncioTimeoutError": SourceFailureCode.TIMEOUT,
    "ReadTimeout": SourceFailureCode.TIMEOUT,
    "ConnectTimeout": SourceFailureCode.TIMEOUT,
    "ClientError": SourceFailureCode.STORAGE_UNAVAILABLE,
    "BotoCoreError": SourceFailureCode.STORAGE_UNAVAILABLE,
    "EndpointConnectionError": SourceFailureCode.STORAGE_UNAVAILABLE,
    "NoSuchKey": SourceFailureCode.STORAGE_UNAVAILABLE,
    "UnsupportedFormatError": SourceFailureCode.UNSUPPORTED_FORMAT,
    "FileNotFoundError": SourceFailureCode.STORAGE_UNAVAILABLE,
    # A misconfigured setting or a missing attribute is an internal defect. It
    # is never the user's file, so it classifies as "analysis unavailable"
    # rather than blaming the upload. This is the exact class that leaked.
    "AttributeError": SourceFailureCode.ANALYSIS_UNAVAILABLE,
    # A credential the provider rejects is also ours, not the user's file. The
    # 4 Aug 2026 incident: a revoked OpenRouter key on the worker service made
    # every embedding call raise `openai.AuthenticationError: 401 {'message':
    # 'User not found.'}`. That message names no key, quota or provider, so the
    # substring table below never matched and it landed in UNKNOWN — which is
    # retryable, so the UI invited a Retry that could only fail identically.
    # Matched by name so this module stays free of the openai/httpx imports.
    "AuthenticationError": SourceFailureCode.ANALYSIS_UNAVAILABLE,
    "PermissionDeniedError": SourceFailureCode.ANALYSIS_UNAVAILABLE,
    "KeyError": SourceFailureCode.ANALYSIS_UNAVAILABLE,
    "ImportError": SourceFailureCode.ANALYSIS_UNAVAILABLE,
    "ModuleNotFoundError": SourceFailureCode.ANALYSIS_UNAVAILABLE,
    "ValidationError": SourceFailureCode.ANALYSIS_UNAVAILABLE,
}

# Substrings checked against the lowercased message, in priority order. Used
# only when the exception type is not decisive.
_BY_MESSAGE: tuple[tuple[tuple[str, ...], SourceFailureCode], ...] = (
    (("unsupported file type", "unsupported format", "cannot parse file type"),
     SourceFailureCode.UNSUPPORTED_FORMAT),
    (("too large", "exceeds maximum size", "file size limit"),
     SourceFailureCode.FILE_TOO_LARGE),
    (("no text", "empty document", "no extractable text", "0 pages"),
     SourceFailureCode.EMPTY_DOCUMENT),
    (("timed out", "timeout", "deadline exceeded"),
     SourceFailureCode.TIMEOUT),
    (("rate limit", "quota", "insufficient_quota", "api key", "openrouter",
      "model not found", "llm", "completion"),
     SourceFailureCode.ANALYSIS_UNAVAILABLE),
    (("nosuchkey", "access denied", "bucket", "s3", "r2 ", "storage"),
     SourceFailureCode.STORAGE_UNAVAILABLE),
    (("could not parse", "parse error", "corrupt", "malformed", "decrypt",
      "password"),
     SourceFailureCode.UNREADABLE_FILE),
)


def classify(exc: BaseException) -> SourceFailureCode:
    """Map an exception onto a user-safe failure code.

    Resolution order is exception type first (most reliable), then message
    substrings, then ``UNKNOWN``. The exception itself is never returned or
    embedded in the result: callers log it separately.
    """
    for klass in type(exc).__mro__:
        code = _BY_EXCEPTION_NAME.get(klass.__name__)
        if code is not None:
            return code

    message = str(exc).lower()
    for needles, code in _BY_MESSAGE:
        if any(needle in message for needle in needles):
            return code

    return SourceFailureCode.UNKNOWN


def classify_and_log(
    exc: BaseException,
    *,
    context: str,
    **fields: object,
) -> SourceFailureCode:
    """Classify ``exc`` and write the raw detail to the structured log.

    This is the only sanctioned path from an exception to a persisted failure
    state. The returned code is safe to store and serve; the traceback, the
    provider operation, and any identifiers stay in the log record.

    ``context`` names the operation ("parse_syllabus"); ``fields`` carry
    identifiers for triage (document_id, course_id) that must not reach the UI.
    """
    code = classify(exc)
    logger.error(
        "%s failed: code=%s exc=%s %s",
        context,
        code.value,
        type(exc).__name__,
        " ".join(f"{key}={value}" for key, value in sorted(fields.items())),
        # Explicit rather than logger.exception(): that resolves exc_info from
        # sys.exc_info(), so it only captures a traceback when called from
        # inside an except block. Passing the exception makes this correct from
        # any call site, and makes the test asserting it non-vacuous.
        exc_info=exc,
    )
    return code
