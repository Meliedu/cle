"""Zip-bomb guard tests for DOCX/PPTX uploads.

Covers :func:`app.services.parser._guard_office_zip`, which refuses Office
archives whose declared uncompressed size exceeds
``_MAX_EXPANDED_BYTES`` (500 MB) — a pre-parse safeguard against
zip-bomb inputs that would OOM the worker when python-docx/python-pptx
materialise the archive.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.services.parser import _guard_office_zip


def test_zipbomb_rejected() -> None:
    """A zip whose declared uncompressed size exceeds the cap is rejected."""
    buf = io.BytesIO()
    # 600 MB of repeating null bytes compresses to tens of KB but declares
    # an uncompressed size well over the 500 MB cap.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("huge.bin", b"0" * (600 * 1024 * 1024))
    with pytest.raises(ValueError, match="expands beyond|oversized entry"):
        _guard_office_zip(buf.getvalue(), "evil.docx")


def test_benign_zip_accepted() -> None:
    """A normal-sized Office archive passes through unchanged."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.xml", b"<xml></xml>")
    _guard_office_zip(buf.getvalue(), "ok.docx")


def test_non_zip_rejected() -> None:
    """Non-zip bytes are surfaced as a clear ValueError, not a raw zip error."""
    with pytest.raises(ValueError, match="not a valid zip"):
        _guard_office_zip(b"not a zip file", "broken.docx")
