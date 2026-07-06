"""courses setup columns

Revision ID: a669b7e5964b
Revises: 71889d907021
Create Date: 2026-07-07 04:22:35.777726

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a669b7e5964b'
down_revision: Union[str, None] = '71889d907021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'courses',
        sa.Column(
            'setup_status', sa.String(length=20),
            server_default=sa.text("'draft'"), nullable=False,
        ),
    )
    op.add_column(
        'courses',
        sa.Column(
            'setup_checklist', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
    )
    op.add_column(
        'courses',
        sa.Column(
            'join_mode', sa.String(length=20),
            server_default=sa.text("'code'"), nullable=False,
        ),
    )
    op.add_column(
        'courses',
        sa.Column(
            'enroll_code_active', sa.Boolean(),
            server_default=sa.text('true'), nullable=False,
        ),
    )
    op.create_check_constraint(
        'ck_courses_setup_status_valid',
        'courses',
        "setup_status IN ('draft','in_review','published')",
    )
    op.create_check_constraint(
        'ck_courses_join_mode_valid',
        'courses',
        "join_mode IN ('code','code_plus_approval')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_courses_join_mode_valid', 'courses', type_='check')
    op.drop_constraint('ck_courses_setup_status_valid', 'courses', type_='check')
    op.drop_column('courses', 'enroll_code_active')
    op.drop_column('courses', 'join_mode')
    op.drop_column('courses', 'setup_checklist')
    op.drop_column('courses', 'setup_status')
