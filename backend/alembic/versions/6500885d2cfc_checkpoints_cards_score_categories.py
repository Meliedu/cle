"""checkpoints, checkpoint_cards, score_categories + concept_tags checkpoint_card

Revision ID: 6500885d2cfc
Revises: 51d14ae61c5f
Create Date: 2026-07-07 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6500885d2cfc'
down_revision: Union[str, None] = '51d14ae61c5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # checkpoints
    # ------------------------------------------------------------------ #
    op.create_table(
        'checkpoints',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('meeting_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column(
            'status', sa.String(length=20), server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('release_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('close_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('close_rule', sa.String(length=20), nullable=True),
        sa.Column(
            'qr_enabled', sa.Boolean(), server_default=sa.text('false'),
            nullable=False,
        ),
        sa.Column('carried_from_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('generation_meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['meeting_id'], ['course_meetings.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['carried_from_id'], ['checkpoints.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "kind IN ('session','follow_up')",
            name='ck_checkpoints_kind_valid',
        ),
        sa.CheckConstraint(
            "status IN ('draft','teacher_editing','approved','scheduled',"
            "'published','live','closed','archived')",
            name='ck_checkpoints_status_valid',
        ),
        sa.CheckConstraint(
            "close_rule IS NULL OR close_rule IN "
            "('manual','at_close_at','end_of_session')",
            name='ck_checkpoints_close_rule_valid',
        ),
        sa.CheckConstraint(
            'carried_from_id IS NULL OR id <> carried_from_id',
            name='ck_checkpoints_no_self_carry',
        ),
    )
    op.create_index(
        'ix_checkpoints_course_id', 'checkpoints', ['course_id'], unique=False
    )

    # ------------------------------------------------------------------ #
    # checkpoint_cards
    # ------------------------------------------------------------------ #
    op.create_table(
        'checkpoint_cards',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('checkpoint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('prompt', sa.String(), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('chunk_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('objective_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            'removed', sa.Boolean(), server_default=sa.text('false'), nullable=False
        ),
        sa.Column('removed_reason', sa.String(length=20), nullable=True),
        sa.Column('removed_note', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['checkpoint_id'], ['checkpoints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['objective_id'], ['learning_objectives.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "kind IN ('review_point','final_comments')",
            name='ck_checkpoint_cards_kind_valid',
        ),
        sa.CheckConstraint(
            "removed_reason IS NULL OR removed_reason IN "
            "('not_needed','duplicate','not_covered','other')",
            name='ck_checkpoint_cards_removed_reason_valid',
        ),
    )
    op.create_index(
        'ix_checkpoint_cards_checkpoint_id', 'checkpoint_cards',
        ['checkpoint_id'], unique=False,
    )
    # Partial unique index: exactly one live final_comments card per checkpoint.
    op.create_index(
        'uq_checkpoint_cards_one_final',
        'checkpoint_cards',
        ['checkpoint_id'],
        unique=True,
        postgresql_where=sa.text("kind = 'final_comments' AND deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------ #
    # score_categories
    # ------------------------------------------------------------------ #
    op.create_table(
        'score_categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('weight', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('points_pool', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('sort', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_score_categories_course_id', 'score_categories', ['course_id'], unique=False
    )

    # ------------------------------------------------------------------ #
    # concept_tags.target_kind — widen CHECK to include 'checkpoint_card'
    # ------------------------------------------------------------------ #
    op.drop_constraint(
        'ck_concept_tags_target_kind_valid', 'concept_tags', type_='check'
    )
    op.create_check_constraint(
        'ck_concept_tags_target_kind_valid',
        'concept_tags',
        "target_kind IN ('chunk','question','flashcard_card','pronunciation_item',"
        "'pool_item','objective','meeting','assignment','checkpoint_card')",
    )


def downgrade() -> None:
    # Revert concept_tags CHECK to the pre-checkpoint_card list.
    op.drop_constraint(
        'ck_concept_tags_target_kind_valid', 'concept_tags', type_='check'
    )
    op.create_check_constraint(
        'ck_concept_tags_target_kind_valid',
        'concept_tags',
        "target_kind IN ('chunk','question','flashcard_card','pronunciation_item',"
        "'pool_item','objective','meeting','assignment')",
    )

    op.drop_index('ix_score_categories_course_id', table_name='score_categories')
    op.drop_table('score_categories')

    op.drop_index('uq_checkpoint_cards_one_final', table_name='checkpoint_cards')
    op.drop_index('ix_checkpoint_cards_checkpoint_id', table_name='checkpoint_cards')
    op.drop_table('checkpoint_cards')

    op.drop_index('ix_checkpoints_course_id', table_name='checkpoints')
    op.drop_table('checkpoints')
