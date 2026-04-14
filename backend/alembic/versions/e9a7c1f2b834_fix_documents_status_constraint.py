"""fix documents status constraint to allow 'ready'

Revision ID: e9a7c1f2b834
Revises: d3e7b8f2a9c4
Create Date: 2026-04-14

The phase1a_hardening migration (a1b2c3d4e5f6) was edited in place to change
'completed' -> 'ready', but databases where it had already been applied kept
the old constraint. The worker writes status='ready' which then fails with
CheckViolationError. This migration replaces the constraint with the correct
allowed values.
"""
from alembic import op


revision = "e9a7c1f2b834"
down_revision = "d3e7b8f2a9c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_documents_status_valid", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_status_valid",
        "documents",
        "status IN ('pending', 'processing', 'ready', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_documents_status_valid", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_status_valid",
        "documents",
        "status IN ('pending', 'processing', 'completed', 'failed')",
    )
