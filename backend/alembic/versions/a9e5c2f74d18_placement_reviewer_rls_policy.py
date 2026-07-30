"""placement: let a reviewer read attempts under RLS

The owner-isolation policy matches the CALLER's ``app.current_user_id``. A
reviewer is never the owner, so under the non-superuser role the original
migration named, the whole CLE review surface would return zero rows: the queue
would be empty, every attempt would 404, and the evidence bundle would show a
NULL response for every question. Silent under-fetch on a decision surface, with
no error anywhere to notice.

Rather than weaken the claim in the docstring, this makes it true. A second
policy admits a caller whose ``app.current_user_role`` is ``instructor``, set
server-side in ``deps.py::get_current_user`` from the User row and never from
anything the client supplies.

Two policies rather than one widened policy, because they answer different
questions -- "is this my row" and "am I allowed to review it" -- and Postgres
ORs permissive policies, which is exactly the semantics wanted. The write path
stays owner-only: a reviewer reads a learner's answers, never edits them.

Revision ID: a9e5c2f74d18
Revises: f2c8d3b71e94
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a9e5c2f74d18"
down_revision: Union[str, None] = "f2c8d3b71e94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("placement_attempts", "placement_responses")


def upgrade() -> None:
    for table in TABLES:
        policy = f"{table}_reviewer_read"
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        # SELECT only. A reviewer's authority is to decide, which is recorded in
        # placement_reviews; it is never to alter what the learner answered.
        op.execute(
            f"CREATE POLICY {policy} ON {table} "
            f"FOR SELECT "
            f"USING (current_setting('app.current_user_role', true) = 'instructor')"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_reviewer_read ON {table}")
