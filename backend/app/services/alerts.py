"""Instructor alert evaluator.

Each rule queries existing data and inserts at most one open InstructorAlert
row per dedupe key ``(course_id, alert_type, target_user_id, dedupe_key)``.
The partial unique index ``uq_instructor_alerts_open_idempotent`` enforces
this with ``NULLS NOT DISTINCT`` so cohort rows (target_user_id IS NULL)
also collide on identical dedupe keys. We catch ``IntegrityError`` on
conflict — codebase precedent in ``concept_clusters.py`` and 6 sibling sites.

Cohort rules pass an explicit ``dedupe_key`` that names the affected object
(e.g. ``concept:<uuid>``, ``quiz:<uuid>``, ``assignment:<uuid>``) so multiple
weak concepts / orphan content / overdue assignments each surface their own
alert instead of being collapsed under one type-level row.

The orchestrator ``evaluate_alerts_for_course`` delegates each rule to a
private helper. Per-student rules use a single aggregating query (one
SELECT per rule) instead of N+1 SELECT-per-student.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, distinct, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    dedupe_key: str = "",
) -> bool:
    """Insert one open alert row; return True if inserted, False on conflict.

    Race-safe via the partial unique index ``uq_instructor_alerts_open_idempotent``
    over ``(course_id, alert_type, target_user_id, dedupe_key) WHERE status='open'``
    with ``NULLS NOT DISTINCT`` so cohort rows (``target_user_id IS NULL``)
    also collide on identical dedupe keys.

    Uses ``ON CONFLICT DO NOTHING ... RETURNING id`` so a duplicate is a no-op
    at the SQL layer — no Python-side ``IntegrityError`` and no rollback. The
    rollback path was the wrong tool here: it expires every ORM object in the
    session, and the orchestrator's loop accesses ``course.id`` / ``course.name``
    on subsequent rules; a refresh in that path raises ``MissingGreenlet``.
    """
    stmt = (
        pg_insert(InstructorAlert)
        .values(
            course_id=course_id,
            instructor_id=instructor_id,
            target_user_id=target_user_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            reason=reason,
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(
            index_elements=[
                "course_id", "alert_type", "target_user_id", "dedupe_key",
            ],
            index_where=text("status = 'open'"),
        )
        .returning(InstructorAlert.id)
    )
    inserted = (await db.execute(stmt)).scalar_one_or_none()
    await db.commit()
    return inserted is not None


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
            dedupe_key=f"concept:{cid}",
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
            dedupe_key=f"concept:{cid}",
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
                dedupe_key=f"meeting:{meeting.id}:prereq:{prereq_id}",
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
            dedupe_key=f"quiz:{qid}",
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
            dedupe_key=f"assignment:{aid}",
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
