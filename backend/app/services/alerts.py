"""Instructor alert evaluator.

Each rule queries existing data and tries to insert one open InstructorAlert
row per dedupe key (course_id, alert_type, target_user_id). The partial
unique index ``uq_instructor_alerts_open_idempotent`` enforces at-most-one
open row per key; we catch IntegrityError on conflict — codebase precedent
in concept_clusters.py and 6 sibling sites.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
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
    # unique index — Postgres treats NULLs as distinct. The migration comment
    # documents this explicitly. Dedupe with a SELECT before insert.
    if target_user_id is None:
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


async def evaluate_alerts_for_course(
    db: AsyncSession, *, course_id: uuid.UUID
) -> dict:
    course = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course is None:
        return {"course_id": str(course_id), "alerts_created": 0}

    now = datetime.now(timezone.utc)
    created = 0

    # --- cohort_concept_weakness ----------------------------------------
    weak = (
        await db.execute(
            select(
                Concept.id, Concept.name,
                func.avg(ConceptMastery.mastery_score).label("avg_m"),
                func.count().filter(
                    (ConceptMastery.mastery_score < 0.5)
                    & (ConceptMastery.confidence >= 0.5)
                ).label("weak_n"),
            )
            .join(ConceptMastery, ConceptMastery.concept_id == Concept.id)
            .where(
                Concept.course_id == course_id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .group_by(Concept.id, Concept.name)
            .having(
                and_(func.avg(ConceptMastery.mastery_score) < 0.4,
                     func.count().filter(
                         (ConceptMastery.mastery_score < 0.5)
                         & (ConceptMastery.confidence >= 0.5)
                     ) >= 3)
            )
        )
    ).all()
    for cid, cname, avg_m, weak_n in weak:
        if await _try_insert(
            db,
            course_id=course_id,
            instructor_id=course.instructor_id,
            target_user_id=None,
            alert_type="cohort_concept_weakness",
            severity="warning",
            title=f"Cohort weak on {cname}",
            reason={
                "concept_id": str(cid),
                "avg_mastery": float(avg_m),
                "weak_students": int(weak_n),
            },
        ):
            created += 1

    # --- content_gap ----------------------------------------------------
    orphans = (
        await db.execute(
            select(Concept.id, Concept.name)
            .outerjoin(ConceptTag, ConceptTag.concept_id == Concept.id)
            .where(
                Concept.course_id == course_id,
                Concept.status == "approved",
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .group_by(Concept.id, Concept.name)
            .having(func.count(ConceptTag.concept_id) == 0)
        )
    ).all()
    for cid, cname in orphans:
        if await _try_insert(
            db,
            course_id=course_id,
            instructor_id=course.instructor_id,
            target_user_id=None,
            alert_type="content_gap",
            severity="info",
            title=f"No content tags reference {cname}",
            reason={"concept_id": str(cid), "concept_name": cname},
        ):
            created += 1

    # --- student_disengaging --------------------------------------------
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)
    enrolled = (
        await db.execute(
            select(Enrollment.user_id).where(
                Enrollment.course_id == course_id,
                Enrollment.role == "student",
            )
        )
    ).scalars().all()
    for uid in enrolled:
        recent = (
            await db.execute(
                select(func.count(QuizAttempt.id))
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(
                    Quiz.course_id == course_id,
                    QuizAttempt.user_id == uid,
                    QuizAttempt.created_at >= seven_days_ago,
                )
            )
        ).scalar_one()
        prior = (
            await db.execute(
                select(func.count(QuizAttempt.id))
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(
                    Quiz.course_id == course_id,
                    QuizAttempt.user_id == uid,
                    QuizAttempt.created_at >= fourteen_days_ago,
                    QuizAttempt.created_at < seven_days_ago,
                )
            )
        ).scalar_one()
        if recent == 0 and prior > 0:
            if await _try_insert(
                db,
                course_id=course_id,
                instructor_id=course.instructor_id,
                target_user_id=uid,
                alert_type="student_disengaging",
                severity="warning",
                title="Student inactive 7d after prior activity",
                reason={"recent": 0, "prior": int(prior)},
            ):
                created += 1

    # --- student_falling_behind -----------------------------------------
    for uid in enrolled:
        late_count = (
            await db.execute(
                select(func.count())
                .select_from(AssignmentSubmission)
                .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
                .where(
                    AssignmentSubmission.user_id == uid,
                    AssignmentSubmission.status == "late",
                    Assignment.course_id == course_id,
                    AssignmentSubmission.updated_at >= fourteen_days_ago,
                )
            )
        ).scalar_one()
        if late_count >= 2:
            if await _try_insert(
                db,
                course_id=course_id,
                instructor_id=course.instructor_id,
                target_user_id=uid,
                alert_type="student_falling_behind",
                severity="warning",
                title=f"{late_count} late submissions in 14d",
                reason={"late_count": int(late_count)},
            ):
                created += 1

    # --- prereq_gap_for_upcoming_meeting --------------------------------
    horizon = now + timedelta(hours=72)
    meetings = (
        await db.execute(
            select(CourseMeeting).where(
                CourseMeeting.course_id == course_id,
                CourseMeeting.scheduled_at.between(now, horizon),
                CourseMeeting.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    enrolled_count = len(enrolled) or 1
    for meeting in meetings:
        # Concepts tagged on this meeting → prereqs that are weak across cohort.
        prereqs = (
            await db.execute(
                select(ConceptPrerequisite.prereq_concept_id, Concept.name)
                .join(
                    ConceptTag,
                    ConceptTag.concept_id == ConceptPrerequisite.dependent_concept_id,
                )
                .join(Concept, Concept.id == ConceptPrerequisite.prereq_concept_id)
                .where(
                    ConceptTag.target_kind == "meeting",
                    ConceptTag.target_id == meeting.id,
                    ConceptPrerequisite.strength >= 0.5,
                )
                .distinct()
            )
        ).all()
        for prereq_id, prereq_name in prereqs:
            n_weak = (
                await db.execute(
                    select(func.count())
                    .select_from(ConceptMastery)
                    .where(
                        ConceptMastery.concept_id == prereq_id,
                        ConceptMastery.course_id == course_id,
                        ConceptMastery.mastery_score < 0.7,
                    )
                )
            ).scalar_one()
            if int(n_weak) * 2 >= enrolled_count:  # 50%+ weak
                if await _try_insert(
                    db,
                    course_id=course_id,
                    instructor_id=course.instructor_id,
                    target_user_id=None,
                    alert_type="prereq_gap_for_upcoming_meeting",
                    severity="warning",
                    title=f"Prereq gap before {meeting.title or 'meeting'}",
                    reason={
                        "meeting_id": str(meeting.id),
                        "prereq_concept_id": str(prereq_id),
                        "prereq_name": prereq_name,
                        "weak_n": int(n_weak),
                        "enrolled": enrolled_count,
                    },
                ):
                    created += 1

    # --- low_quiz_participation -----------------------------------------
    quizzes = (
        await db.execute(
            select(Quiz).where(
                Quiz.course_id == course_id,
                Quiz.is_published.is_(True),
                Quiz.created_at < seven_days_ago,
                Quiz.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for quiz in quizzes:
        n_attempters = (
            await db.execute(
                select(func.count(func.distinct(QuizAttempt.user_id))).where(
                    QuizAttempt.quiz_id == quiz.id
                )
            )
        ).scalar_one()
        if int(n_attempters) * 100 < enrolled_count * 30:  # <30%
            if await _try_insert(
                db,
                course_id=course_id,
                instructor_id=course.instructor_id,
                target_user_id=None,
                alert_type="low_quiz_participation",
                severity="info",
                title=f"<30% attempted '{quiz.title}'",
                reason={
                    "quiz_id": str(quiz.id),
                    "attempters": int(n_attempters),
                    "enrolled": enrolled_count,
                },
            ):
                created += 1

    # --- missed_deadline -----------------------------------------------
    one_day_ago = now - timedelta(hours=24)
    overdue = (
        await db.execute(
            select(Assignment).where(
                Assignment.course_id == course_id,
                Assignment.due_at < one_day_ago,
                Assignment.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for asn in overdue:
        n_submitted = (
            await db.execute(
                select(func.count(AssignmentSubmission.user_id)).where(
                    AssignmentSubmission.assignment_id == asn.id,
                    AssignmentSubmission.status.in_(("submitted", "graded")),
                )
            )
        ).scalar_one()
        if int(n_submitted) * 100 < enrolled_count * 80:  # <80%
            if await _try_insert(
                db,
                course_id=course_id,
                instructor_id=course.instructor_id,
                target_user_id=None,
                alert_type="missed_deadline",
                severity="critical",
                title=f"<80% turned in '{asn.title}'",
                reason={
                    "assignment_id": str(asn.id),
                    "submitted": int(n_submitted),
                    "enrolled": enrolled_count,
                },
            ):
                created += 1

    return {"course_id": str(course_id), "alerts_created": created}
