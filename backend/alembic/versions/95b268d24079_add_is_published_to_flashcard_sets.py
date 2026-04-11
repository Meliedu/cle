"""add is_published to flashcard_sets

Revision ID: 95b268d24079
Revises: 9b049e07c22e
Create Date: 2026-04-10 00:31:19.832209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '95b268d24079'
down_revision: Union[str, None] = '9b049e07c22e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing flashcard sets stay visible (server_default='true').
    # New sets created via the ORM default to is_published=False (draft).
    op.add_column(
        'flashcard_sets',
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )


def downgrade() -> None:
    op.drop_column('flashcard_sets', 'is_published')
