"""QR launch token signing + the launch gate (P3 T9).

The teacher launches a checkpoint's QR: this mints a signed, window-bound token
(PyJWT HS256, mirroring ``canvas_oauth.encode_state``) and persists a single
active ``checkpoint_launches`` row. Students scan the QR and hit the T10
``/attend/{token}`` endpoint, which verifies the token with
``decode_launch_token``.

Design decisions carried here:

* **Signing secret** is ``settings.checkpoint_token_secret`` — the ≥32-byte
  validation mirrors ``canvas_state_secret`` but is enforced *at launch time*
  (not at startup) so dev/test stay bootable with checkpoints unconfigured. An
  unconfigured/too-short secret **fails closed** with ``QRNotAvailable``.
* **The gate** refuses (``QRNotAvailable``) unless the checkpoint is
  ``published``/``live`` + session-bound (has a meeting) + ``qr_enabled`` + inside
  its release..close window — the endpoint maps this to the ``QR_NOT_AVAILABLE``
  typed code the mobile flow switches on.
* **Single active launch** per checkpoint is enforced by the partial unique
  index ``(checkpoint_id) WHERE status='active'`` (T4). A ``rotate`` closes the
  prior launch (``status='closed'``) then issues a fresh token with a new
  ``launch_id``/``jti``.
* **Window** — ``window_start`` is the launch moment; ``window_end`` is the
  checkpoint's ``close_at`` when it is set and still in the future, else a
  bounded default. The token's ``exp`` echoes ``window_end`` so an expired token
  fails to decode.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.attendance import CheckpointLaunch
from app.models.checkpoint import Checkpoint
from app.services.checkpoint_responses import is_within_window

#: Minimum signing-secret length, matching ``canvas_state_secret`` (32 bytes).
MIN_SECRET_BYTES = 32

#: Checkpoint statuses that may be QR-launched (§4.2 — live to students).
LAUNCHABLE_STATUSES: frozenset[str] = frozenset({"published", "live"})

#: Bounded default launch window when the checkpoint has no ``close_at`` (a
#: manual-close checkpoint). Keeps the token short-lived rather than unbounded.
DEFAULT_WINDOW_SECONDS = 4 * 3600


class QRNotAvailable(Exception):
    """The checkpoint cannot currently be QR-launched (typed gate refusal).

    The endpoint maps this to the ``QR_NOT_AVAILABLE`` code (§3.4) the mobile
    flow switches on to render "not open yet / not configured" states.
    """

    code = "QR_NOT_AVAILABLE"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class LaunchTokenInvalid(Exception):
    """A launch token failed to verify (expired, tampered, or unverifiable)."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_secret() -> str:
    """Return the signing secret, or raise ``QRNotAvailable`` (fail closed).

    Mirrors ``canvas_oauth``'s ≥32-byte check, but enforced here at launch time
    rather than at startup so an unconfigured deployment stays bootable.
    """
    secret = settings.checkpoint_token_secret
    if not secret or len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise QRNotAvailable("QR check-in is not configured on this server.")
    return secret


def encode_launch_token(payload: dict) -> str:
    """Sign a launch token (PyJWT HS256). ``payload`` must carry ``exp``."""
    return jwt.encode(payload, _require_secret(), algorithm="HS256")


def decode_launch_token(token: str) -> dict:
    """Verify signature + expiry and return the claims.

    Raises ``LaunchTokenInvalid`` on any failure (bad signature, expired ``exp``,
    or an unconfigured secret). The raw PyJWT message is never surfaced — it can
    include token fragments — but the chain is preserved for tooling.
    """
    try:
        secret = _require_secret()
    except QRNotAvailable as exc:
        raise LaunchTokenInvalid("launch token verification unavailable") from exc
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise LaunchTokenInvalid("launch token verification failed") from exc


def _derive_window_end(checkpoint: Checkpoint, now: datetime) -> datetime:
    """The QR window's end (== the token ``exp``).

    Uses the checkpoint's ``close_at`` when it is set and still in the future;
    otherwise a bounded default so the token is never unbounded and always
    ``exp``-in-the-future (a decodable token at issue time).
    """
    if checkpoint.close_at is not None and checkpoint.close_at > now:
        return checkpoint.close_at
    return now + timedelta(seconds=DEFAULT_WINDOW_SECONDS)


def _assert_launchable(checkpoint: Checkpoint, now: datetime) -> None:
    """The launch gate (§3.4). Raises ``QRNotAvailable`` on any failure."""
    if checkpoint.status not in LAUNCHABLE_STATUSES:
        raise QRNotAvailable("This checkpoint is not published.")
    if checkpoint.meeting_id is None:
        raise QRNotAvailable("This checkpoint is not attached to a session.")
    if not checkpoint.qr_enabled:
        raise QRNotAvailable("QR check-in is not enabled for this checkpoint.")
    if not is_within_window(checkpoint, now):
        raise QRNotAvailable("This checkpoint is not open right now.")


async def _active_launch(
    db: AsyncSession, checkpoint_id: uuid.UUID
) -> CheckpointLaunch | None:
    return (
        await db.execute(
            sa.select(CheckpointLaunch).where(
                CheckpointLaunch.checkpoint_id == checkpoint_id,
                CheckpointLaunch.status == "active",
            )
        )
    ).scalar_one_or_none()


async def _close_active_launches(db: AsyncSession, checkpoint_id: uuid.UUID) -> None:
    """Close every active launch for a checkpoint (rotate step).

    Flushes so the fresh active INSERT does not trip the partial unique index
    against a still-active prior row within the same transaction.
    """
    await db.execute(
        sa.update(CheckpointLaunch)
        .where(
            CheckpointLaunch.checkpoint_id == checkpoint_id,
            CheckpointLaunch.status == "active",
        )
        .values(status="closed")
    )
    await db.flush()


async def launch_checkpoint(
    db: AsyncSession,
    *,
    checkpoint: Checkpoint,
    launched_by: uuid.UUID,
    rotate: bool = False,
    now: datetime | None = None,
) -> CheckpointLaunch:
    """Gate + sign + persist a QR launch for a checkpoint.

    Raises ``QRNotAvailable`` when the gate refuses, when the signing secret is
    unconfigured (fail closed), or when a live launch already exists and
    ``rotate`` was not requested. On ``rotate`` the prior active launch is closed
    first, then a fresh token (new ``launch_id``/``jti``) is issued.
    """
    now = now or _utcnow()
    _assert_launchable(checkpoint, now)
    # Validate the secret before any DB write — fail closed without side effects.
    _require_secret()

    existing = await _active_launch(db, checkpoint.id)
    if existing is not None:
        if not rotate:
            raise QRNotAvailable(
                "A QR is already active for this checkpoint; rotate to issue a "
                "new one."
            )
        await _close_active_launches(db, checkpoint.id)

    launch_id = uuid.uuid4()
    jti = uuid.uuid4().hex
    window_start = now
    window_end = _derive_window_end(checkpoint, now)
    token = encode_launch_token(
        {
            "launch_id": str(launch_id),
            "checkpoint_id": str(checkpoint.id),
            "meeting_id": str(checkpoint.meeting_id),
            "jti": jti,
            "exp": int(window_end.timestamp()),
        }
    )

    launch = CheckpointLaunch(
        id=launch_id,
        checkpoint_id=checkpoint.id,
        meeting_id=checkpoint.meeting_id,
        token=token,
        jti=jti,
        window_start=window_start,
        window_end=window_end,
        launched_by=launched_by,
        status="active",
    )
    db.add(launch)
    try:
        await db.commit()
    except IntegrityError as exc:
        # A concurrent launch won the partial unique index race — fail closed
        # with the same typed refusal the pre-check gives.
        await db.rollback()
        raise QRNotAvailable(
            "A QR is already active for this checkpoint; rotate to issue a new "
            "one."
        ) from exc
    await db.refresh(launch)
    return launch
