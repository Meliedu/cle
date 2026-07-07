"""enrollments status column

Revision ID: fe73ccfab9f9
Revises: 6500885d2cfc
Create Date: 2026-07-07 08:32:23.064577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe73ccfab9f9'
down_revision: Union[str, None] = '6500885d2cfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enrollment lifecycle status (Decision 1). server_default='active' backfills
    # every existing row (instructor self-enroll, prior student joins, Canvas
    # roster claims, PendingEnrollment claims) with zero behavior change.
    op.add_column(
        "enrollments",
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="active"
        ),
    )
    op.create_check_constraint(
        "ck_enrollments_status_valid",
        "enrollments",
        "status IN ('pending','active','rejected')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_enrollments_status_valid", "enrollments", type_="check"
    )
    op.drop_column("enrollments", "status")
