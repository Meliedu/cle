"""quiz publish-settings + assessment_purpose columns

Revision ID: f7a3c9e1b024
Revises: e6c2b8f4a19d
Create Date: 2026-07-08 12:00:00.000000

P5 Task B1 (Decision 1): practice-vs-graded is a DEDICATED new
``quizzes.assessment_purpose`` column (CHECK ``practice|graded``,
``server_default='practice'`` so every existing quiz backfills to practice) —
the existing ``purpose`` (CHECK ``after_class|live``) and the unconstrained
legacy ``quiz_type`` are left untouched. Alongside it ride the §4.5
publish-settings: ``score_bearing``, ``score_category_id`` (FK), ``points``,
``grading_mode`` (CHECK ``auto|manual|participation``), ``open_at/due_at/close_at``,
and ``late_rule`` (CHECK ``accept_late|reject_late|accept_with_flag``).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f7a3c9e1b024'
down_revision: Union[str, None] = 'e6c2b8f4a19d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'quizzes',
        sa.Column(
            'assessment_purpose', sa.String(length=20),
            server_default=sa.text("'practice'"), nullable=False,
        ),
    )
    op.add_column(
        'quizzes',
        sa.Column(
            'score_bearing', sa.Boolean(),
            server_default=sa.text('false'), nullable=False,
        ),
    )
    op.add_column(
        'quizzes',
        sa.Column(
            'score_category_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('score_categories.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.add_column(
        'quizzes',
        sa.Column('points', sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column(
        'quizzes',
        sa.Column('grading_mode', sa.String(length=20), nullable=True),
    )
    op.add_column(
        'quizzes',
        sa.Column('open_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'quizzes',
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'quizzes',
        sa.Column('close_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'quizzes',
        sa.Column('late_rule', sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        'ck_quizzes_assessment_purpose_valid',
        'quizzes',
        "assessment_purpose IN ('practice','graded')",
    )
    op.create_check_constraint(
        'ck_quizzes_grading_mode_valid',
        'quizzes',
        "grading_mode IN ('auto','manual','participation')",
    )
    op.create_check_constraint(
        'ck_quizzes_late_rule_valid',
        'quizzes',
        "late_rule IN ('accept_late','reject_late','accept_with_flag')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_quizzes_late_rule_valid', 'quizzes', type_='check')
    op.drop_constraint('ck_quizzes_grading_mode_valid', 'quizzes', type_='check')
    op.drop_constraint(
        'ck_quizzes_assessment_purpose_valid', 'quizzes', type_='check'
    )
    op.drop_column('quizzes', 'late_rule')
    op.drop_column('quizzes', 'close_at')
    op.drop_column('quizzes', 'due_at')
    op.drop_column('quizzes', 'open_at')
    op.drop_column('quizzes', 'grading_mode')
    op.drop_column('quizzes', 'points')
    op.drop_column('quizzes', 'score_category_id')
    op.drop_column('quizzes', 'score_bearing')
    op.drop_column('quizzes', 'assessment_purpose')
