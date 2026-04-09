"""hybrid search: tsvector trigger and backfill

Revision ID: 219a6239faac
Revises: 505ded56ba1e
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '219a6239faac'
down_revision: Union[str, None] = '505ded56ba1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Backfill tsvector_content for existing chunks
    op.execute("""
        UPDATE chunks
        SET tsvector_content = to_tsvector('english', content)
        WHERE tsvector_content IS NULL
    """)

    # 2. GIN index for fast full-text search
    op.execute("""
        CREATE INDEX idx_chunks_tsvector ON chunks USING GIN (tsvector_content)
    """)

    # 3. Create trigger function that auto-populates tsvector_content
    op.execute("""
        CREATE OR REPLACE FUNCTION chunks_tsvector_trigger()
        RETURNS trigger AS $$
        BEGIN
            NEW.tsvector_content := to_tsvector('english', NEW.content);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # 4. Create trigger on chunks table
    op.execute("""
        CREATE TRIGGER tsvector_update
        BEFORE INSERT OR UPDATE OF content ON chunks
        FOR EACH ROW
        EXECUTE FUNCTION chunks_tsvector_trigger()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tsvector_update ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsvector_trigger()")
    op.execute("DROP INDEX IF EXISTS idx_chunks_tsvector")
    op.execute("UPDATE chunks SET tsvector_content = NULL")
