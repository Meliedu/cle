"""Instructor alert evaluator.

Each rule queries existing data and tries to insert one open InstructorAlert
row per dedupe key (course_id, alert_type, target_user_id). The partial
unique index ``uq_instructor_alerts_open_idempotent`` enforces at-most-one
open row per key; we catch IntegrityError on conflict — codebase precedent
in concept_clusters.py and 6 sibling sites.

The orchestrator ``evaluate_alerts_for_course`` delegates each rule to a
private helper. Per-student rules use a single aggregating query (one
SELECT per rule) instead of N+1 SELECT-per-student.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, distinct, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    AssignmentSubmission,
    Concept,
    ConceptMastery,
    ConceptPrerequisite,
    ConceptTag,
    Course,
    CourseMeeting,
    Enrollment,
    InstructorAlert,
    Quiz,
    QuizAttempt,
)

logger = logging.getLogger(__name__)


async def _try_insert(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
    instructor_id: uuid.UUID,
    target_user_id: uuid.UUID | None,
    alert_type: str,
    severity: str,
    title: str,
    reason: dict,
) -> bool:
    # Cohort alerts (target_user_id IS NULL) are NOT deduped by the partial
    # unique index — Postgres treats NULLs as distinct, so ON CONFLICT can't
    # serialize concurrent inserts. Acquire a per-(course_id, alert_type)
    # transaction-scoped advisory lock to make the SELECT-then-INSERT atomic
    # against concurrent workers; the lock auto-releases on commit/rollback.
    if target_user_id is None:
        h = hashlib.blake2b(digest_size=8)
        h.update(course_id.bytes)
        h.update(alert_type.encode("utf-8"))
        # bigint range: mask top bit so the value fits a signed bigint.
        lock_key = int.from_bytes(h.digest(), "big") & 0x7FFFFFFFFFFFFFFF
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key}
        )

        existing = (
            await db.execute(
                select(InstructorAlert.id).where(
                    InstructorAlert.course_id == course_id,
                    InstructorAlert.alert_type == alert_type,
                    InstructorAlert.target_user_id.is_(None),
                    InstructorAlert.status == "open",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False

    db.add(
        InstructorAlert(
            course_id=course_id,
            instructor_id=instructor_id,
            target_user_id=target_user_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            reason=reason,
        )
    )
    try:
        await db.commit()
        return True
    except IntegrityError:
        # Per-student alerts hit the partial unique index → roll back and
        # treat as no-op. Cohort alerts can't reach this branch (we returned
        # False above), but keep the catch for safety against races.
        await db.rollback()
        return False


async def _rule_cohort_concept_weakness(
    db: AsyncSession,
    *,
    course: Course,
    instructor_id: uuid.UUID,
) -> int:
    weak_filter = (
        (ConceptMastery.mastery_score < 0.5)
        & (ConceptMastery.confidence >= 0.5)
    )
    weak_n = func.count().filter(weak_filter)
    avg_m = func.avg(ConceptMastery.mastery_score)

    rows = (
        await db.execute(
            select(
                Concept.id, Concept.name,
                avg_m.label("avg_m"),
                weak_n.label("weak_n"),
            )
            .join(ConceptMastery, ConceptMastery.concept_id == Concept.id)
            .where(
                Concept.course_id == course.id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .group_by(Concept.id, Concept.name)
            .having(and_(avg_m < 0.4, weak_n >= 3))
        )
    ).all()

    created = 0
    for cid, cname, avg_value, n_weak in rows:
        if await _try_insert(
            db,
            course_id=course.id,
            instructor_id=instructor_id,
            target_user_id=None,
            alert_type="cohort_concept_weakness",
            severity="warning",
            title=f"Cohort weak on {cname}",
            reason={
                "concept_id": str(cid),
                "avg_mastery": float(avg_value),
                "weak_students": int(n_weak),
            },
        ):
            created += 1
    return created


async def _rule_content_gap(
    db: AsyncSession,
    *,
    course: Course,
    instructor_id: uuid.UUID,
) -> int:
    rows = (
        await db.execute(
            select(Concept.id, Concept.name)
            .outerjoin(ConceptTag, ConceptTag.concept_id == Concept.id)
            .where(
                Concept.course_id == course.id,
                Concept.status == "approved",
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .group_by(Concept.id, Concept.name)
            .having(func.count(ConceptTag.concept_id) == 0)
        )
    ).all()

    created = 0
    for cid, cname in rows:
        if await _try_insert(
            db,
            course_id=course.id,
            instructor_id=instructor_id,
            target_user_id=None,
            alert_type="content_gap",
            severity="info",
            title=f"No content tags reference {cname}",
            reason={"concept_id": str(cid), "concept_name": cname},
        ):
            created += 1
    return created


async def _rule_student_disengaging(
    db: AsyncSession,
    *,
    course: Course,
    instructor_id: uuid.UUID,
    now: datetime,
) -> int:
    """One aggregating query: per-student recent vs prior quiz-attempt counts.

    Replaces 2N SELECTs (recent + prior per enrolled student) with a single
    GROUP BY having recent=0 AND prior>0. The OUTER JOIN on QuizAttempt
    keeps students with zero recent activity in the result set.
    """
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)

    recent_count = func.count(QuizAttempt.id).filter(
        QuizAttempt.created_at >= seven_days_ago
    )
    prior_count = func.count(QuizAttempt.id).filter(
        and_(
            QuizAttempt.created_at >= fourteen_days_ago,
            QuizAttempt.created_at < seven_days_ago,
        )
    )

    rows = (
        await db.execute(
            select(
                Enrollment.user_id,
                recent_count.label("recent"),
                prior_count.label("prior"),
            )
            .join(Quiz, Quiz.course_id == Enrollment.course_id)
            .outerjoin(
                QuizAttempt,
                and_(
                    QuizAttempt.quiz_id == Quiz.id,
                    QuizAttempt.user_id == Enrollment.user_id,
                ),
            )
            .where(
                Enrollment.course_id == course.id,
                Enrollment.role == "student",
                Quiz.deleted_at.is_(None),
            )
            .group_by(Enrollment.user_id)
            .having(and_(recent_count == 0, prior_count > 0))
        )
    ).all()

    created = 0
    for uid, recent, prior in rows:
        if await _try_insert(
            db,
            course_id=course.id,
            instructor_id=instructor_id,
            target_user_id=uid,
            alert_type="student_disengaging",
            severity="warning",
            title="Student inactive 7d after prior activity",
            reason={"recent": int(recent), "prior": int(prior)},
        ):
            created += 1
    return created


async def _rule_student_falling_behind(
    db: AsyncSession,
    *,
    course: Course,
    instructor_id: uuid.UUID,
    now: datetime,
) -> int:
    """One aggregating query: per-student late submission count in last 14d.

    Recency window is on Assignment.due_at, not AssignmentSubmission.updated_at:
    updated_at is set when mark_overdue_submissions flips status to 'late', which
    reflects cron run time — not how recently the student missed the deadline.

    Replaces N SELECTs (one per enrolled student) with a single GROUP BY
    having late_count >= 2.
    """
    fourteen_days_ago = now - timedelta(days=14)
    late_count = func.count()

    rows = (
        await db.execute(
            select(
                AssignmentSubmission.user_id,
                late_count.label("late_n"),
            )
            .join(
                Assignment, Assignment.id == AssignmentSubmission.assignment_id
            )
            .where(
                AssignmentSubmission.status == "late",
                Assignment.course_id == course.id,
                Assignment.due_at >= fourteen_days_ago,
                Assignment.deleted_at.is_(None),
            )
            .group_by(AssignmentSubmission.user_id)
            .having(late_count >= 2)
        )
    ).all()

    created = 0
    for uid, n_late in rows:
        if await _try_insert(
            db,
            course_id=course.id,
            instructor_id=instructor_id,
            target_user_id=uid,
            alert_type="student_falling_behind",
            severity="warning",
            title=f"{int(n_late)} late submissions in 14d",
            reason={"late_count": int(n_late)},
        ):
            created += 1
    return created


async def _rule_prereq_gap_for_upcoming_meeting(
    db: AsyncSession,
    *,
    course: Course,
    instructor_id: uuid.UUID,
    enrolled_count: int,
    now: datetime,
) -> int:
    """One query per upcoming meeting: prereqs × cohort weak counts.

    Replaces 2-level N+1 (prereqs per meeting + COUNT per prereq) with a
    single GROUP BY HAVING for the cohort weak-count. The outer loop
    (one query per upcoming meeting) is intentional — meetings differ in
    their tagged-concept set.
    """
    horizon = now + timedelta(hours=72)
    meetings = (
        await db.execute(
            select(CourseMeeting).where(
                CourseMeeting.course_id == course.id,
                CourseMeeting.scheduled_at.between(now, horizon),
                CourseMeeting.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    created = 0
    n_weak = func.count().filter(ConceptMastery.mastery_score < 0.7)
    for meeting in meetings:
        rows = (
            await db.execute(
                select(
                    ConceptPrerequisite.prereq_concept_id,
                    Concept.name,
                    n_weak.label("weak_n"),
                )
                .join(
                    ConceptTag,
                    ConceptTag.concept_id == ConceptPrerequisite.dependent_concept_id,
                )
                .join(
                    Concept, Concept.id == ConceptPrerequisite.prereq_concept_id
                )
                .outerjoin(
                    ConceptMastery,
                    and_(
                        ConceptMastery.concept_id
                        == ConceptPrerequisite.prereq_concept_id,
                        ConceptMastery.course_id == course.id,
                    ),
                )
                .where(
                    ConceptTag.target_kind == "meeting",
                    ConceptTag.target_id == meeting.id,
                    ConceptPrerequisite.strength >= 0.5,
                )
                .group_by(ConceptPrerequisite.prereq_concept_id, Concept.name)
                .having(n_weak * 2 >= enrolled_count)  # ≥50% weak
            )
        ).all()
        for prereq_id, prereq_name, weak in rows:
            if await _try_insert(
                db,
                course_id=course.id,
                instructor_id=instructor_id,
                target_user_id=None,
                alert_type="prereq_gap_for_upcoming_meeting",
                severity="warning",
                title=f"Prereq gap before {meeting.title or 'meeting'}",
                reason={
                    "meeting_id": str(meeting.id),
                    "prereq_concept_id": str(prereq_id),
                    "prereq_name": prereq_name,
                    "weak_n": int(weak),
                    "enrolled": enrolled_count,
                },
            ):
                created += 1
    return created


async def _rule_low_quiz_participation(
    db: AsyncSession,
    *,
    course: Course,
    instructor_id: uuid.UUID,
    enrolled_count: int,
    now: datetime,
) -> int:
    """One aggregating query: per-quiz unique-attempter count + threshold filter.

    Replaces N+1 (one COUNT per published quiz) with a single GROUP BY HAVING.
    """
    seven_days_ago = now - timedelta(days=7)
    n_attempters = func.count(distinct(QuizAttempt.user_id))
    rows = (
        await db.execute(
            select(Quiz.id, Quiz.title, n_attempters.label("attempters"))
            .outerjoin(QuizAttempt, QuizAttempt.quiz_id == Quiz.id)
            .where(
                Quiz.course_id == course.id,
                Quiz.is_published.is_(True),
                Quiz.created_at < seven_days_ago,
                Quiz.deleted_at.is_(None),
            )
            .group_by(Quiz.id, Quiz.title)
            .having(n_attempters * 100 < enrolled_count * 30)
        )
    ).all()

    created = 0
    for qid, title, n in rows:
        if await _try_insert(
            db,
            course_id=course.id,
            instructor_id=instructor_id,
            target_user_id=None,
            alert_type="low_quiz_participation",
            severity="info",
            title=f"<30% attempted '{title}'",
            reason={
                "quiz_id": str(qid),
                "attempters": int(n),
                "enrolled": enrolled_count,
            },
        ):
            created += 1
    return created


async def _rule_missed_deadline(
    db: AsyncSession,
    *,
    course: Course,
    instructor_id: uuid.UUID,
    enrolled_count: int,
    now: datetime,
) -> int:
    """One aggregating query: per-assignment submitted-count + threshold filter.

    Replaces N+1 (one COUNT per overdue assignment) with a single GROUP BY
    HAVING. Also bounds recency to the past 30 days so old assignments
    don't keep surfacing every evaluator run.
    """
    one_day_ago = now - timedelta(hours=24)
    thirty_days_ago = now - timedelta(days=30)
    n_submitted = func.count(AssignmentSubmission.user_id).filter(
        AssignmentSubmission.status.in_(("submitted", "graded"))
    )
    rows = (
        await db.execute(
            select(Assignment.id, Assignment.title, n_submitted.label("submitted_n"))
            .outerjoin(
                AssignmentSubmission,
                AssignmentSubmission.assignment_id == Assignment.id,
            )
            .where(
                Assignment.course_id == course.id,
                Assignment.due_at < one_day_ago,
                Assignment.due_at >= thirty_days_ago,
                Assignment.deleted_at.is_(None),
            )
            .group_by(Assignment.id, Assignment.title)
            .having(n_submitted * 100 < enrolled_count * 80)
        )
    ).all()

    created = 0
    for aid, title, n in rows:
        if await _try_insert(
            db,
            course_id=course.id,
            instructor_id=instructor_id,
            target_user_id=None,
            alert_type="missed_deadline",
            severity="critical",
            title=f"<80% turned in '{title}'",
            reason={
                "assignment_id": str(aid),
                "submitted": int(n),
                "enrolled": enrolled_count,
            },
        ):
            created += 1
    return created


async def evaluate_alerts_for_course(
    db: AsyncSession, *, course_id: uuid.UUID
) -> dict:
    course = (
        await db.execute(
            select(Course).where(
                Course.id == course_id,
                Course.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if course is None:
        return {"course_id": str(course_id), "alerts_created": 0}

    now = datetime.now(timezone.utc)
    enrolled_count = (
        await db.execute(
            select(func.count(Enrollment.user_id)).where(
                Enrollment.course_id == course_id,
                Enrollment.role == "student",
            )
        )
    ).scalar_one() or 1

    instructor_id = course.instructor_id
    created = 0
    created += await _rule_cohort_concept_weakness(
        db, course=course, instructor_id=instructor_id
    )
    created += await _rule_content_gap(
        db, course=course, instructor_id=instructor_id
    )
    created += await _rule_student_disengaging(
        db, course=course, instructor_id=instructor_id, now=now
    )
    created += await _rule_student_falling_behind(
        db, course=course, instructor_id=instructor_id, now=now
    )
    created += await _rule_prereq_gap_for_upcoming_meeting(
        db,
        course=course,
        instructor_id=instructor_id,
        enrolled_count=enrolled_count,
        now=now,
    )
    created += await _rule_low_quiz_participation(
        db,
        course=course,
        instructor_id=instructor_id,
        enrolled_count=enrolled_count,
        now=now,
    )
    created += await _rule_missed_deadline(
        db,
        course=course,
        instructor_id=instructor_id,
        enrolled_count=enrolled_count,
        now=now,
    )
    return {"course_id": str(course_id), "alerts_created": created}
