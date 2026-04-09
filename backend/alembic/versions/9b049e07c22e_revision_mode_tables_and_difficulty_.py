"""revision mode tables and difficulty columns

Revision ID: 9b049e07c22e
Revises: 3f8a2b1c9d7e
Create Date: 2026-04-09 19:29:50.859664

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9b049e07c22e'
down_revision: Union[str, None] = '3f8a2b1c9d7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New tables
    op.create_table('bandit_models',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('content_type', sa.String(length=20), nullable=False),
    sa.Column('weights', sa.LargeBinary(), nullable=False),
    sa.Column('strategy', sa.String(length=10), nullable=False),
    sa.Column('reward_mean', sa.Float(), nullable=False),
    sa.Column('reward_var', sa.Float(), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'course_id', 'content_type')
    )
    op.create_table('revision_sessions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('content_type', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('items_answered', sa.Integer(), nullable=False),
    sa.Column('total_score', sa.Numeric(precision=7, scale=2), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('revision_pool_items',
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('content_type', sa.String(length=20), nullable=False),
    sa.Column('difficulty', sa.String(length=10), nullable=False),
    sa.Column('question_text', sa.String(), nullable=True),
    sa.Column('options', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('correct_answer', sa.String(length=10), nullable=True),
    sa.Column('explanation', sa.String(), nullable=True),
    sa.Column('front', sa.String(), nullable=True),
    sa.Column('back', sa.String(), nullable=True),
    sa.Column('target_text', sa.String(), nullable=True),
    sa.Column('language', sa.String(length=20), nullable=True),
    sa.Column('source_chunk_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_chunk_id'], ['chunks.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('revision_attempts',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('session_id', sa.UUID(), nullable=False),
    sa.Column('pool_item_id', sa.UUID(), nullable=False),
    sa.Column('content_type', sa.String(length=20), nullable=False),
    sa.Column('difficulty', sa.String(length=10), nullable=False),
    sa.Column('score', sa.Numeric(precision=3, scale=2), nullable=False),
    sa.Column('time_taken_ms', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.ForeignKeyConstraint(['pool_item_id'], ['revision_pool_items.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['revision_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('revision_item_served',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('pool_item_id', sa.UUID(), nullable=False),
    sa.Column('served_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['pool_item_id'], ['revision_pool_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'pool_item_id')
    )

    # Difficulty columns on existing tables (with server_default for existing rows)
    op.add_column('questions', sa.Column('difficulty', sa.String(length=10), server_default='medium', nullable=False))
    op.add_column('flashcard_cards', sa.Column('difficulty', sa.String(length=10), server_default='medium', nullable=False))

    # Custom indexes for revision queries
    op.execute("""
        CREATE INDEX idx_revision_pool_course_type_diff
        ON revision_pool_items (course_id, content_type, difficulty)
    """)
    op.execute("""
        CREATE INDEX idx_revision_attempts_state_vector
        ON revision_attempts (user_id, course_id, content_type, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_revision_attempts_state_vector")
    op.execute("DROP INDEX IF EXISTS idx_revision_pool_course_type_diff")
    op.drop_column('flashcard_cards', 'difficulty')
    op.drop_column('questions', 'difficulty')
    op.drop_table('revision_item_served')
    op.drop_table('revision_attempts')
    op.drop_table('revision_pool_items')
    op.drop_table('revision_sessions')
    op.drop_table('bandit_models')
