"""Course-setup wizard state + the server-side course-open gate (spec §3.4/§4.8).

Decision 1: ``courses.context_status`` remains the single authoritative
course-open gate; ``setup_status`` is the wizard lifecycle. Publish flips both;
reopen only rolls back ``setup_status`` so enrolled students stay in (§4.8).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course

# Step flags stored in ``courses.setup_checklist`` (§4.8). Ordered as the wizard
# renders them; ``analyzer_review`` gates on the analyze job, ``checkpoints`` on
# the generate job, both reviewed by the teacher.
SETUP_STEP_KEYS: tuple[str, ...] = (
    "basics",
    "syllabus",
    "materials",
    "schedule",
    "analyzer_review",
    "ilo_map",
    "checkpoints",
    "score_policy",
    "class_code",
)


class SetupGateError(Exception):
    """Raised when a gate refuses. ``code`` is the typed error the UI maps.

    The router layer (Task 8) maps ``code`` into the ``APIResponse`` envelope's
    ``error`` field so the wizard can branch on it (e.g. ``SETUP_NOT_OPEN``,
    ``SETUP_INCOMPLETE``).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def missing_steps(course: Course) -> list[str]:
    """Return the ordered setup steps not yet marked complete."""
    checklist = course.setup_checklist or {}
    return [k for k in SETUP_STEP_KEYS if not checklist.get(k)]


async def set_step_flag(
    db: AsyncSession, course: Course, key: str, value: bool
) -> Course:
    """Mark a single wizard step complete/incomplete in ``setup_checklist``.

    Immutable update: builds a fresh dict so SQLAlchemy flags the JSONB column
    dirty (in-place mutation of the existing dict would not be detected).
    """
    if key not in SETUP_STEP_KEYS:
        raise SetupGateError("UNKNOWN_STEP", f"Unknown setup step '{key}'")
    checklist = {**(course.setup_checklist or {}), key: bool(value)}
    course.setup_checklist = checklist
    if course.setup_status == "draft" and any(checklist.values()):
        course.setup_status = "in_review"
    await db.commit()
    await db.refresh(course)
    return course


async def publish_setup(db: AsyncSession, course: Course) -> Course:
    """Publish the course: flip both gates in one transaction (Decision 1).

    Raises ``SETUP_INCOMPLETE`` (leaving all state untouched) if any wizard step
    is still outstanding.
    """
    missing = missing_steps(course)
    if missing:
        raise SetupGateError(
            "SETUP_INCOMPLETE",
            f"Setup cannot publish; incomplete steps: {', '.join(missing)}",
        )
    course.setup_status = "published"
    course.context_status = "approved"  # Decision 1: single authoritative gate
    course.context_approved_at = _utcnow()
    await db.commit()
    await db.refresh(course)
    return course


async def reopen_setup(db: AsyncSession, course: Course) -> Course:
    """Reopen the wizard without locking enrolled students out (§4.8).

    Rolls ``setup_status`` back to ``in_review`` (or ``draft`` if nothing is
    checked) but leaves ``context_status`` at ``approved`` so the course stays
    open — reopening only re-flags artifacts whose sources changed.
    """
    checklist = course.setup_checklist or {}
    course.setup_status = "in_review" if any(checklist.values()) else "draft"
    await db.commit()
    await db.refresh(course)
    return course


def assert_course_open(course: Course) -> None:
    """Reusable course-open gate (P2 enrollment + P3 workspace access).

    Raises ``SETUP_NOT_OPEN`` unless ``context_status == 'approved'`` — the
    single authority per Decision 1. Returns ``None`` when the gate passes.
    """
    if course.context_status != "approved":
        raise SetupGateError("SETUP_NOT_OPEN", "This course is not open yet.")
