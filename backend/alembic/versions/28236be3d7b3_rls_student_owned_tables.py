"""rls student owned tables

Revision ID: 28236be3d7b3
Revises: 8231060f9c65
Create Date: 2026-04-13 20:16:35.071691

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28236be3d7b3'
down_revision: Union[str, None] = '8231060f9c65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RLS_TABLES: tuple[tuple[str, str], ...] = (
    ("student_progress", "user_id"),
    ("quiz_attempts", "user_id"),
    ("flashcard_progress", "user_id"),
)


def upgrade() -> None:
    for table, owner_col in RLS_TABLES:
        policy = f"{table}_owner_isolation"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"CREATE POLICY {policy} ON {table} "
            f"FOR ALL "
            f"USING ({owner_col} = current_setting('app.current_user_id', true)::uuid) "
            f"WITH CHECK ({owner_col} = current_setting('app.current_user_id', true)::uuid)"
        )

    op.execute("ALTER ROLE postgres BYPASSRLS")


def downgrade() -> None:
    for table, _owner_col in RLS_TABLES:
        policy = f"{table}_owner_isolation"
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
