"""syllabus_imports: typed error_code, and scrub leaked exception text

The approved UI/UX handoff requires that raw exception text, provider
operation names, object keys, and stack names stay in structured server logs
and never reach user copy. ``syllabus_imports.error_message`` violated that:
``run_parse_syllabus`` stored ``str(exc)`` there and the API served it verbatim,
so an instructor saw

    AttributeError: 'Settings' object has no attribute 'llm_primary_model'

This migration:
  1. adds ``error_code`` for the typed ``SourceFailureCode`` value the UI maps
     to safe copy, and
  2. backfills it for existing failed rows, then NULLs ``error_message`` on
     those rows so the leaked text is removed from the database rather than
     merely hidden by the new frontend.

Step 2 is deliberate data loss of a field that should never have been
populated. The information is not lost for operators: the same failures were
already written to the structured application log by ``logger.exception``.

Revision ID: a7c4e91d3f80
Revises: d5e8b3a6f214
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7c4e91d3f80"
down_revision = "d5e8b3a6f214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "syllabus_imports",
        sa.Column("error_code", sa.String(length=40), nullable=True),
    )
    # Documents carry the same typed code so the setup Sources stage can render
    # per-source recovery copy without ever reading a backend message.
    op.add_column(
        "documents",
        sa.Column("error_code", sa.String(length=40), nullable=True),
    )
    # Existing failed documents have no recorded cause. `unknown` maps to
    # retryable generic copy, which is the correct default: the recovery path
    # (retry, or replace the file) exists regardless of the original cause.
    op.execute(
        "UPDATE documents SET error_code = 'unknown' WHERE status = 'failed'"
    )

    # Backfill a best-effort code from the legacy text so existing failed
    # imports still render actionable copy, then remove the text itself.
    #
    # The ordering of the CASE arms matters: an internal defect (an exception
    # class name) is classified as analysis_unavailable rather than blamed on
    # the instructor's file.
    op.execute(
        """
        UPDATE syllabus_imports
        SET error_code = CASE
            WHEN error_message IS NULL THEN NULL
            WHEN error_message ~ '^[A-Z][A-Za-z]*(Error|Exception):'
                THEN 'analysis_unavailable'
            WHEN lower(error_message) LIKE '%missing or kind changed%'
              OR lower(error_message) LIKE '%course mismatch%'
                THEN 'not_found'
            WHEN lower(error_message) LIKE '%timeout%'
              OR lower(error_message) LIKE '%timed out%'
                THEN 'timeout'
            WHEN lower(error_message) LIKE '%unsupported%'
                THEN 'unsupported_format'
            WHEN lower(error_message) LIKE '%too large%'
                THEN 'file_too_large'
            WHEN lower(error_message) LIKE '%no text%'
              OR lower(error_message) LIKE '%empty%'
                THEN 'empty_document'
            WHEN lower(error_message) LIKE '%bucket%'
              OR lower(error_message) LIKE '%storage%'
              OR lower(error_message) LIKE '%nosuchkey%'
                THEN 'storage_unavailable'
            WHEN lower(error_message) LIKE '%parse%'
              OR lower(error_message) LIKE '%corrupt%'
                THEN 'unreadable_file'
            ELSE 'unknown'
        END
        WHERE status = 'failed'
        """
    )

    # Scrub the leaked internals. Only failed rows ever carried exception text.
    op.execute(
        "UPDATE syllabus_imports SET error_message = NULL WHERE status = 'failed'"
    )


def downgrade() -> None:
    # The scrubbed text is not recoverable, and reinstating it would reintroduce
    # the leak. Downgrade drops the typed columns only.
    op.drop_column("documents", "error_code")
    op.drop_column("syllabus_imports", "error_code")
