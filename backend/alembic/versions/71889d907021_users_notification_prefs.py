"""users.notification_prefs

Revision ID: 71889d907021
Revises: a1f0e0d20002
Create Date: 2026-07-07 02:36:24.289912

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '71889d907021'
down_revision: Union[str, None] = 'a1f0e0d20002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Whitelisted notification preferences stored as JSONB on users. JSONB
    # (not JSON) so the PATCH endpoint can merge submitted keys atomically
    # server-side with the `||` concatenation operator, avoiding the
    # read-modify-write lost-update window. Existing rows default to '{}'.
    op.add_column(
        'users',
        sa.Column(
            'notification_prefs',
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'notification_prefs')
