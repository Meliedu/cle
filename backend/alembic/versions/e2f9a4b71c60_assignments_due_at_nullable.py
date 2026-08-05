"""assignments: let a graded component exist without a due date

A syllabus routinely weights work it never dates: "Attendance and
Participation, 15%", "Final exam, 25%" with the date set by the registrar
later. MGMT2130 lists five graded components and dates one of them.

``due_at`` was ``NOT NULL``, so the syllabus applier had to skip every
undated component (``services/syllabus.py``, "Skipping assignment ... with
invalid due_at"). After the parse path was fixed to keep those components,
the instructor saw "5 assignments" in the import preview, applied it, and got
one assignment with no explanation: a silent partial write, which is worse
than the loud failure it replaced.

Nothing downstream needed the column to be mandatory. ``_resolve_submission_
status`` already takes ``due_at: datetime | None`` and returns early on None;
``mark_overdue_submissions`` and the calendar range query filter on
comparisons that simply exclude NULL; the list endpoint orders by ``due_at``,
which Postgres sorts NULLS LAST on ASC. So an undated assignment is inert
everywhere that depends on a deadline, which is exactly right: it carries a
weight and a title, and it never becomes overdue.

Widening a NOT NULL to nullable is backward compatible for readers and needs
no data backfill. The downgrade cannot be exact: it has to invent a date for
any row that has none, so it refuses instead, rather than silently stamping
real rows with a fabricated deadline.

Revision ID: e2f9a4b71c60
Revises: b7d4e1c09a35
Create Date: 2026-08-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2f9a4b71c60"
down_revision = "b7d4e1c09a35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "assignments",
        "due_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    # Refuse rather than fabricate: a NOT NULL restore would have to write a
    # deadline onto rows whose whole point is not having one, and those rows
    # are indistinguishable afterwards.
    undated = op.get_bind().execute(
        sa.text("SELECT count(*) FROM assignments WHERE due_at IS NULL")
    ).scalar_one()
    if undated:
        raise RuntimeError(
            f"{undated} assignment(s) have no due_at. Give them a date or "
            "delete them before downgrading; this migration will not invent one."
        )
    op.alter_column(
        "assignments",
        "due_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
