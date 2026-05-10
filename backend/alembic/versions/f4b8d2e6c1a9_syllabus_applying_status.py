"""syllabus_imports: add 'applying' status for atomic apply

Revision ID: f4b8d2e6c1a9
Revises: e2a4c6f8d1b3
Create Date: 2026-05-10

The apply endpoint did SELECT-status-then-apply-then-UPDATE-status without
a row lock. Two concurrent applies could each pass the ``status == 'parsed'``
check and both run ``apply_syllabus_payload``, double-creating modules /
meetings / objectives / assignments because the applier dedupes by
select-then-insert (no DB-level uniqueness).

Add an ``applying`` state so the apply endpoint can transition
``parsed -> applying`` with a conditional UPDATE; only the first request
wins, the rest get a 409.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f4b8d2e6c1a9"
down_revision: Union[str, None] = "e2a4c6f8d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_syllabus_imports_status_valid", "syllabus_imports", type_="check"
    )
    op.create_check_constraint(
        "ck_syllabus_imports_status_valid",
        "syllabus_imports",
        "status IN ('pending','parsed','applying','applied','failed','superseded')",
    )


def downgrade() -> None:
    # Reset any in-flight 'applying' rows so the old constraint accepts
    # them. Best-effort: in practice these rows should be either
    # finalized to 'applied' or 'failed' before downgrade, but we don't
    # want to fail a downgrade because of an orphan row.
    op.execute(
        "UPDATE syllabus_imports SET status = 'failed' WHERE status = 'applying'"
    )
    op.drop_constraint(
        "ck_syllabus_imports_status_valid", "syllabus_imports", type_="check"
    )
    op.create_check_constraint(
        "ck_syllabus_imports_status_valid",
        "syllabus_imports",
        "status IN ('pending','parsed','applied','failed','superseded')",
    )
