"""Add tasks.error_code and stop serving raw exception text from /api/rag.

``tasks.error_message`` holds ``"{ExceptionClass}: {message}"`` (see
``worker._sanitize_error_message``), and ``GET /api/rag/jobs/{id}`` returned it
verbatim as ``error``. That is the same defect the ``documents`` and
``syllabus_imports`` columns were introduced to fix: a job that failed on a
misconfiguration answered with

    AttributeError: 'Settings' object has no attribute 'llm_primary_model'

The frontend filtered it, so users were protected by the client alone while the
server half of the contract was missing.

This adds the typed column, backfills existing failed rows by mapping the
recorded exception class to a ``SourceFailureCode``, and leaves
``error_message`` intact for server-side triage (it is no longer serialised).

Revision ID: b8d2f5c31a90
Revises: a7c4e91d3f80
"""

from alembic import op
import sqlalchemy as sa

revision = "b8d2f5c31a90"
down_revision = "a7c4e91d3f80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("error_code", sa.String(40), nullable=True))

    # Backfill from the exception class name already recorded in
    # error_message. The mapping mirrors app/services/failures.py::classify;
    # anything unrecognised becomes 'unknown' so the UI always has a code to
    # map rather than a NULL it must special-case.
    op.execute(
        r"""
        UPDATE tasks
        SET error_code = CASE
            WHEN error_message IS NULL THEN 'unknown'
            WHEN error_message ~* '^(TimeoutError|asyncio\.TimeoutError)' THEN 'timeout'
            WHEN error_message ~* '^(ConnectionError|ClientConnector|OSError|BotoCoreError|ClientError)' THEN 'storage_unavailable'
            WHEN error_message ~* '^(AttributeError|KeyError|ImportError|NameError|TypeError)' THEN 'analysis_unavailable'
            WHEN error_message ~* '^(ValueError|JSONDecodeError|UnicodeDecodeError)' THEN 'unreadable_file'
            WHEN error_message ~* 'not found' THEN 'not_found'
            ELSE 'unknown'
        END
        WHERE status = 'failed'
        """
    )


def downgrade() -> None:
    op.drop_column("tasks", "error_code")
