"""QR attendance scan (P3 T10).

The student scans the teacher's QR and hits ``POST /api/attend/{token}``. This
module resolves the launch token to its ``checkpoint_launches`` row, derives the
``present``/``late`` status, and upserts a single ``attendance_records`` row.

Design decisions carried here:

* **Token proves signature + expiry only.** Revocation-on-rotate is visible
  only on the launch row (``status='closed'``), so a decoded token is looked up
  by ``jti`` and its row must still be ``active`` — otherwise ``LaunchClosed``.
* **present vs late** mirrors ``checkpoint_responses`` exactly: past the
  checkpoint's ``close_at`` is ``late`` (reachable while the launch row is still
  active and the token still decodable — e.g. the QR window/``exp`` outlives the
  checkpoint's ``close_at``); otherwise ``present``.
* **Single-use per student** — the upsert is ``on_conflict_do_nothing`` on the
  ``(meeting_id, user_id)`` unique constraint, so a second scan is an idempotent
  no-op: the first check-in wins (a later scan never downgrades it).
* **Participation ONLY** — attendance NEVER emits a ``learning_event`` or
  enqueues mastery. The evidence seam is deliberately absent here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord, CheckpointLaunch
from app.models.checkpoint import Checkpoint
from app.services.checkpoint_qr import (
    LAUNCHABLE_STATUSES,
    LaunchTokenInvalid,
    decode_launch_token,
)


class LaunchClosed(Exception):
    """The launch token is well-signed but its launch is no longer scannable.

    Raised when the ``jti`` has no launch row (never issued / wrong server) or
    the row was rotated/closed (``status != 'active'``). The endpoint maps this
    to the typed ``LAUNCH_CLOSED`` 409 the mobile flow switches on.
    """

    code = "LAUNCH_CLOSED"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class CheckpointNotLaunchable(LaunchClosed):
    """The launch is ``active`` but its checkpoint is no longer launchable.

    Scan-time defense-in-depth (P7 B11, Decision 8a): even when the
    ``checkpoint_launches`` row is still ``active``, a scan is refused if the
    checkpoint itself has left the ``published``/``live`` window (moved back to
    ``draft``/``teacher_editing``/``approved``/``archived`` or soft-deleted) —
    e.g. a stale launch that was never closed. Participation is only recorded for
    a launchable checkpoint. Subclasses ``LaunchClosed`` (it IS a
    no-longer-scannable launch) but carries a distinct code so the mobile flow
    can tell "checkpoint closed under you" from "token rotated".
    """

    code = "CHECKPOINT_NOT_LIVE"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def derive_scan_status(close_at: datetime | None, now: datetime) -> str:
    """``present`` unless the scan lands past the checkpoint's ``close_at``.

    Mirrors ``checkpoint_responses``' on_time/late derivation (there it is
    ``on_time``/``late``; attendance uses the ``present``/``late`` vocabulary of
    the ``attendance_records`` status CHECK).
    """
    if close_at is not None and now > close_at:
        return "late"
    return "present"


async def resolve_active_launch(
    db: AsyncSession, token: str
) -> tuple[CheckpointLaunch, dict]:
    """Verify the token and return its ``active`` launch row + claims.

    Raises ``LaunchTokenInvalid`` (bad signature / expired / tampered /
    unconfigured secret) or ``LaunchClosed`` (missing or non-active row).
    """
    claims = decode_launch_token(token)  # raises LaunchTokenInvalid
    jti = claims.get("jti")
    if not jti:
        raise LaunchTokenInvalid("launch token is missing its identifier")
    launch = (
        await db.execute(
            sa.select(CheckpointLaunch).where(CheckpointLaunch.jti == jti)
        )
    ).scalar_one_or_none()
    if launch is None or launch.status != "active":
        raise LaunchClosed("This QR launch is no longer active.")
    return launch, claims


async def record_scan(
    db: AsyncSession,
    *,
    launch: CheckpointLaunch,
    checkpoint: Checkpoint,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> AttendanceRecord:
    """Idempotently upsert the student's QR attendance row.

    First scan wins: ``on_conflict_do_nothing`` on ``(meeting_id, user_id)``
    means a second scan re-fetches the existing row without mutating it (so a
    later scan never downgrades ``present`` to ``late``). Participation only —
    no learning_event / mastery is ever emitted here.
    """
    # Scan-time checkpoint re-check (P7 B11, Decision 8a): the active launch row
    # is not sufficient — the checkpoint must ITSELF still be launchable. Refuse
    # (writing NO attendance) if it was moved out of published/live or
    # soft-deleted while a stale launch lingered active.
    if checkpoint.deleted_at is not None or checkpoint.status not in LAUNCHABLE_STATUSES:
        raise CheckpointNotLaunchable(
            "This checkpoint is no longer open for check-in."
        )

    now = now or _utcnow()
    status = derive_scan_status(checkpoint.close_at, now)

    stmt = (
        pg_insert(AttendanceRecord)
        .values(
            id=uuid.uuid4(),
            meeting_id=launch.meeting_id,
            user_id=user_id,
            status=status,
            source="qr",
            checked_in_at=now,
        )
        .on_conflict_do_nothing(index_elements=["meeting_id", "user_id"])
    )
    await db.execute(stmt)
    await db.commit()

    row = (
        await db.execute(
            sa.select(AttendanceRecord).where(
                AttendanceRecord.meeting_id == launch.meeting_id,
                AttendanceRecord.user_id == user_id,
            )
        )
    ).scalar_one()
    return row
