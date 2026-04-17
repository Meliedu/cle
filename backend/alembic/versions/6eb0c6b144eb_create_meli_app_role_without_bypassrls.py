"""create meli_app role without bypassrls

The production app pool should run under a non-superuser so that RLS
policies (e.g. ``student_owned_tables``) are actually enforced instead of
silently bypassed. Creating the role here — rather than as a manual DBA
step — ensures every deployment gets the correct permissions without
extra operator setup.

The role is created with ``LOGIN`` but without a password. Operators set
the password out of band (``ALTER ROLE meli_app PASSWORD '<strong>';``)
and wire it into ``DATABASE_URL``. Downgrade revokes grants and drops
the role.

Revision ID: 6eb0c6b144eb
Revises: 6c391255c4f6
Create Date: 2026-04-16 21:52:46.299762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6eb0c6b144eb'
down_revision: Union[str, None] = '6c391255c4f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent role creation — DO block guards against "role already exists"
    # on rerun (useful for local dev where the role may outlive a database
    # reset). Explicitly no BYPASSRLS, no SUPERUSER, no CREATEDB, no CREATEROLE.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='meli_app') THEN
                CREATE ROLE meli_app LOGIN;
            END IF;
        END $$;
        """
    )
    op.execute("GRANT CONNECT ON DATABASE langassistant TO meli_app")
    op.execute("GRANT USAGE ON SCHEMA public TO meli_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        "TO meli_app"
    )
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO meli_app"
    )
    # Future tables created by later migrations inherit the same grants so we
    # don't have to remember to re-grant after every schema change.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO meli_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO meli_app"
    )


def downgrade() -> None:
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM meli_app")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM meli_app")
    op.execute("REVOKE ALL ON SCHEMA public FROM meli_app")
    op.execute("REVOKE ALL ON DATABASE langassistant FROM meli_app")
    op.execute("DROP ROLE IF EXISTS meli_app")
