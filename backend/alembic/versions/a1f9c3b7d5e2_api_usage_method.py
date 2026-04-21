"""add method column to api_usage

The rate limiter enforces two independent caps on ``/api/rag/*``:

* Non-GET (LLM generation) — per-hour cap (50 instructor / 10 student).
* GET (summary reads, job polling) — per-minute cap of 60.

Before this migration, the middleware computed both caps by counting *every*
row in ``api_usage`` within the relevant window, with no HTTP method filter.
That meant a burst of GET polls (e.g. frontend polling a long-running
generation job every few seconds) would also consume the hourly POST quota,
causing legitimate generation requests to be rejected with 429 even though
the user had not made anywhere near the generation-cap-worth of POSTs.

Adding an explicit ``method`` column lets the middleware count each cap
against only its own traffic class. Existing rows are backfilled by URL
prefix: ``/api/rag/jobs/`` and ``/api/rag/course-summary/`` are GET-only
endpoints, everything else under ``/api/rag/`` is a POST.

Revision ID: a1f9c3b7d5e2
Revises: 6eb0c6b144eb
Create Date: 2026-04-21 09:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1f9c3b7d5e2"
down_revision: Union[str, None] = "6eb0c6b144eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOT NULL with a permanent server_default. Two reasons the default must
    # stay in place, not just be used for backfill:
    #   1. Rolling deploys: Railway keeps the old backend container serving
    #      while the new one starts. During that overlap the old code inserts
    #      ``ApiUsage`` rows WITHOUT a ``method`` value. Without a default
    #      those inserts would violate NOT NULL, the middleware's fail-closed
    #      branch would fire, and every ``/api/rag/*`` request would return
    #      503 until the new container took over.
    #   2. Worker/other services that import the ApiUsage model but lag a
    #      release would hit the same NOT NULL error on insert.
    # The new middleware code always supplies ``method`` explicitly, so the
    # default only ever fires during rollover or for out-of-band inserts.
    op.add_column(
        "api_usage",
        sa.Column(
            "method",
            sa.String(length=8),
            nullable=False,
            server_default="POST",
        ),
    )

    # Retrofit historical GET rows so the rate limiter's first count after
    # deployment reflects reality rather than penalising every past poll as a
    # generation call.
    op.execute(
        """
        UPDATE api_usage
           SET method = 'GET'
         WHERE endpoint LIKE '/api/rag/jobs/%'
            OR endpoint LIKE '/api/rag/course-summary/%'
        """
    )


def downgrade() -> None:
    op.drop_column("api_usage", "method")
