"""course enroll_code

Revision ID: c2e5f8a1b3d9
Revises: b7d4a9e2c1f3
Create Date: 2026-04-14 10:00:00.000000

"""
from typing import Sequence, Union

import secrets
import string

from alembic import op
import sqlalchemy as sa


revision: str = "c2e5f8a1b3d9"
down_revision: Union[str, None] = "b7d4a9e2c1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Avoid ambiguous chars (0/O, 1/I/L). Uppercase-only so codes are easy to dictate.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("enroll_code", sa.String(length=16), nullable=True),
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM courses WHERE enroll_code IS NULL")).fetchall()
    used: set[str] = set()
    for (course_id,) in rows:
        while True:
            code = _generate_code()
            if code in used:
                continue
            used.add(code)
            break
        bind.execute(
            sa.text("UPDATE courses SET enroll_code = :code WHERE id = :id"),
            {"code": code, "id": course_id},
        )

    op.alter_column("courses", "enroll_code", nullable=False)
    op.create_unique_constraint(
        "uq_courses_enroll_code", "courses", ["enroll_code"]
    )
    op.create_index(
        "idx_courses_enroll_code", "courses", ["enroll_code"], unique=True
    )


def downgrade() -> None:
    op.drop_index("idx_courses_enroll_code", table_name="courses")
    op.drop_constraint("uq_courses_enroll_code", "courses", type_="unique")
    op.drop_column("courses", "enroll_code")
