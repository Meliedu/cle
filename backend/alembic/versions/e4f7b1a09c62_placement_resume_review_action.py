"""placement: allow the resume_review decision

``technical_review`` was a trap state. The transition table allowed an exit,
but no review action mapped to one, so the only decision a reviewer could
legally record was ``invalidate`` -- on exactly the attempts where something had
gone wrong through no fault of the learner, and where invalidating used to lock
them out of the test entirely.

``resume_review`` returns such an attempt to the normal queue once the fault is
understood, so the reviewer can then approve or override it like any other.

Revision ID: e4f7b1a09c62
Revises: c1a7f4e93b25
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e4f7b1a09c62"
down_revision: Union[str, None] = "c1a7f4e93b25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "'approve','override','request_advising','invalidate','release'"
_NEW = _OLD + ",'resume_review'"


def upgrade() -> None:
    op.drop_constraint(
        "ck_placement_reviews_action_valid", "placement_reviews", type_="check"
    )
    op.create_check_constraint(
        "ck_placement_reviews_action_valid",
        "placement_reviews",
        f"action IN ({_NEW})",
    )


def downgrade() -> None:
    # A recorded resume_review row would violate the narrower constraint, so
    # rewrite those rows to the closest legal predecessor rather than failing
    # the downgrade outright.
    op.execute(
        "UPDATE placement_reviews SET action = 'request_advising' "
        "WHERE action = 'resume_review'"
    )
    op.drop_constraint(
        "ck_placement_reviews_action_valid", "placement_reviews", type_="check"
    )
    op.create_check_constraint(
        "ck_placement_reviews_action_valid",
        "placement_reviews",
        f"action IN ({_OLD})",
    )
