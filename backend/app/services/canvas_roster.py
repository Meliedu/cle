"""Canvas roster → Meli enrollment diff + pre-provisioning."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Enrollment, PendingEnrollment, User
from app.services.canvas_client import CanvasClient

logger = logging.getLogger(__name__)


CANVAS_ROLE_TO_MELI: dict[str, str] = {
    "TeacherEnrollment": "instructor",
    "TaEnrollment": "instructor",
    "StudentEnrollment": "student",
    # DesignerEnrollment + ObserverEnrollment intentionally omitted.
}


@dataclass
class RosterDiff:
    added: int = 0
    unchanged: int = 0
    dropped: int = 0
    pending: int = 0
    skipped_off_domain: int = 0
    errors: list[dict] = field(default_factory=list)


def _allowed_domains() -> set[str]:
    raw = settings.allowed_email_domains or ""
    return {d.strip().lower() for d in raw.split(",") if d.strip()}


def _email_in_domain(email: str, allowed: set[str]) -> bool:
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[1].lower() in allowed


async def sync_roster(
    db: AsyncSession,
    client: CanvasClient,
    meli_course_id: uuid.UUID,
    canvas_course_id: str,
    send_invite_emails: bool,
    preserve_user_ids: set[uuid.UUID] | None = None,
) -> RosterDiff:
    """Reconcile a Meli course's enrollments with its Canvas roster.

    - Match by lowercased email against existing Meli users → insert
      ``Enrollment`` rows with mapped role.
    - Misses (unknown email) → upsert ``PendingEnrollment`` so the user is
      auto-claimed at first login (see ``app.api.deps.get_current_user``).
    - Drops (active Meli enrollment whose email is no longer in Canvas) →
      hard-delete. Quiz/flashcard history references ``user_id`` directly,
      so it is preserved.
    - Off-domain emails are counted but never auto-provisioned.
    - ``preserve_user_ids`` enrollments are never dropped — typically used to
      protect the instructor who linked the course from being removed if
      Canvas omits them from the enrollment list.
    """
    preserve_user_ids = preserve_user_ids or set()
    diff = RosterDiff()
    enrollments = await client.list_course_enrollments(canvas_course_id)
    allowed = _allowed_domains()

    desired: dict[str, dict] = {}
    for e in enrollments:
        user_blob = e.get("user") or {}
        email = (
            user_blob.get("email") or e.get("login_id") or ""
        ).strip().lower()
        if not email:
            continue
        # Off-domain emails get counted regardless of role — they would never
        # be auto-provisioned anyway, but the count signals to the instructor
        # that these existed in Canvas.
        if not _email_in_domain(email, allowed):
            diff.skipped_off_domain += 1
            continue
        meli_role = CANVAS_ROLE_TO_MELI.get(e.get("type") or "")
        if meli_role is None:
            continue
        desired[email] = {
            "role": meli_role,
            "canvas_user_id": str(e.get("user_id", "")),
        }

    existing_rows = (
        await db.execute(
            select(Enrollment, User).join(User, Enrollment.user_id == User.id)
            .where(Enrollment.course_id == meli_course_id)
        )
    ).all()
    existing_by_email = {u.email.lower(): enr for enr, u in existing_rows}
    preserved_emails = {
        u.email.lower() for _, u in existing_rows if u.id in preserve_user_ids
    }

    existing_pending = (
        await db.execute(
            select(PendingEnrollment).where(
                PendingEnrollment.course_id == meli_course_id
            )
        )
    ).scalars().all()
    pending_by_email = {p.email.lower(): p for p in existing_pending}

    want_emails = set(desired.keys())
    have_active = set(existing_by_email.keys())
    new_emails = want_emails - have_active

    if new_emails:
        user_rows = (
            await db.execute(
                select(User).where(User.email.in_(list(new_emails)))
            )
        ).scalars().all()
        users_by_email = {u.email.lower(): u for u in user_rows}
    else:
        users_by_email = {}

    now = datetime.now(timezone.utc)
    pending_invites: list[str] = []

    for email in new_emails:
        spec = desired[email]
        user = users_by_email.get(email)
        if user is not None:
            db.add(
                Enrollment(
                    course_id=meli_course_id, user_id=user.id, role=spec["role"]
                )
            )
            diff.added += 1
            stale_pending = pending_by_email.pop(email, None)
            if stale_pending is not None:
                await db.delete(stale_pending)
        else:
            stmt = pg_insert(PendingEnrollment).values(
                course_id=meli_course_id,
                email=email,
                canvas_user_id=spec["canvas_user_id"],
                role=spec["role"],
                invited_at=now if send_invite_emails else None,
            ).on_conflict_do_update(
                index_elements=["course_id", "email"],
                set_={
                    "canvas_user_id": spec["canvas_user_id"],
                    "role": spec["role"],
                    **({"invited_at": now} if send_invite_emails else {}),
                },
            )
            await db.execute(stmt)
            diff.pending += 1
            pending_invites.append(email)

    diff.unchanged = len(want_emails & have_active)

    dropped_emails = (have_active - want_emails) - preserved_emails
    for email in dropped_emails:
        enr = existing_by_email[email]
        await db.execute(
            delete(Enrollment).where(Enrollment.id == enr.id)
        )
        diff.dropped += 1

    await db.commit()

    if send_invite_emails:
        for email in pending_invites:
            # TODO(canvas): wire to actual mail provider; logged for now.
            logger.info("Would send Meli invite to %s", email)

    return diff
