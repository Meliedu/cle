"""cron_runs: durable cron watermarks

Revision ID: e2a4c6f8d1b3
Revises: d1e3f5a8c4b9
Create Date: 2026-05-10

Cron tick scheduling lives in worker memory: ``_initial_watermarks`` seeds
each watermark to ``now`` on boot, and ``_tick_*`` helpers advance the
watermark unconditionally — even when the body raises. Net effect: a
restart just before a daily tick delays the job up to 24 h, repeated
deploys can starve a job indefinitely, and transient DB errors aren't
retried until the next cadence interval.

Move watermarks into ``cron_runs`` so workers share state, advancement
happens only after success, and a per-name ``pg_try_advisory_xact_lock``
serializes concurrent runs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2a4c6f8d1b3"
down_revision: Union[str, None] = "d1e3f5a8c4b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cron_runs",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column(
            "last_success_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("cron_runs")
