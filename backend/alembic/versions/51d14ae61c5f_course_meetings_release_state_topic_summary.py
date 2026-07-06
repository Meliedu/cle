"""course_meetings release_state + topic_summary

Revision ID: 51d14ae61c5f
Revises: a669b7e5964b
Create Date: 2026-07-07 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '51d14ae61c5f'
down_revision: Union[str, None] = 'a669b7e5964b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'course_meetings',
        sa.Column(
            'release_state', sa.String(length=20),
            server_default=sa.text("'locked'"), nullable=False,
        ),
    )
    op.add_column(
        'course_meetings',
        sa.Column('topic_summary', sa.String(), nullable=True),
    )
    op.create_check_constraint(
        'ck_course_meetings_release_state_valid',
        'course_meetings',
        "release_state IN ('locked','released','completed','archived')",
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_course_meetings_release_state_valid', 'course_meetings', type_='check'
    )
    op.drop_column('course_meetings', 'topic_summary')
    op.drop_column('course_meetings', 'release_state')
