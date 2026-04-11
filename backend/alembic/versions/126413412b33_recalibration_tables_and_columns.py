"""recalibration tables and columns

Revision ID: 126413412b33
Revises: 95b268d24079
Create Date: 2026-04-12 00:12:42.329957

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '126413412b33'
down_revision: Union[str, None] = '95b268d24079'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- New table: recalibration_stats ---
    op.create_table(
        'recalibration_stats',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('pool_item_id', sa.UUID(), nullable=False),
        sa.Column('course_id', sa.UUID(), nullable=False),
        sa.Column('content_type', sa.String(length=20), nullable=False),
        sa.Column('llm_difficulty', sa.String(length=10), nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('correct_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('hard_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('score_sum', sa.Numeric(precision=10, scale=2), server_default=sa.text('0'), nullable=False),
        sa.Column('score_sq_sum', sa.Numeric(precision=12, scale=4), server_default=sa.text('0'), nullable=False),
        sa.ForeignKeyConstraint(['pool_item_id'], ['revision_pool_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pool_item_id'),
    )
    op.execute(
        "CREATE INDEX idx_recal_stats_course "
        "ON recalibration_stats (course_id, content_type, llm_difficulty)"
    )

    # --- New table: recalibration_models ---
    op.create_table(
        'recalibration_models',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('course_id', sa.UUID(), nullable=False),
        sa.Column('content_type', sa.String(length=20), nullable=False),
        sa.Column('dirichlet_params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('transition_matrix', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('items_used', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column(
            'total_attempts_since_last_run',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('course_id', 'content_type'),
    )

    # --- New columns on revision_pool_items ---
    op.add_column(
        'revision_pool_items',
        sa.Column('recalibrated_difficulty', sa.String(length=10), nullable=True),
    )
    op.add_column(
        'revision_pool_items',
        sa.Column('recalibration_confidence', sa.Numeric(precision=4, scale=3), nullable=True),
    )
    op.add_column(
        'revision_pool_items',
        sa.Column(
            'instructor_override',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )

    # --- New column on revision_attempts ---
    op.add_column(
        'revision_attempts',
        sa.Column('corrected_difficulty', sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    # Remove column from revision_attempts
    op.drop_column('revision_attempts', 'corrected_difficulty')

    # Remove columns from revision_pool_items
    op.drop_column('revision_pool_items', 'instructor_override')
    op.drop_column('revision_pool_items', 'recalibration_confidence')
    op.drop_column('revision_pool_items', 'recalibrated_difficulty')

    # Drop tables (index is dropped automatically with the table)
    op.execute("DROP INDEX IF EXISTS idx_recal_stats_course")
    op.drop_table('recalibration_models')
    op.drop_table('recalibration_stats')
