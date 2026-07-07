"""Score-record aggregation (P5 B11).

Builds each active student's per-category / per-artifact grade rollup from the
two score-bearing evidence sources:

* GRADED quizzes (``Quiz.assessment_purpose == 'graded'``) → the student's BEST
  ``QuizAttempt.score`` (a 0–100 percentage). ``earned_points`` scales the
  quiz's ``points`` by that percentage.
* SCORE-BEARING activities (``Activity.score_bearing is True``) → activities are
  PARTICIPATION-ONLY (Decision 5), so a submitted ``ActivityResponse`` earns the
  activity's full ``points``; no response earns 0.

Artifacts are bucketed by ``score_category_id`` (uncategorized → a ``None``
bucket). Only categories that actually carry a score-bearing artifact appear.

Pure aggregation — no HTTP resolution, no commit. The teacher route feeds every
active student; the student route feeds only the caller (S059). Read of the
student-owned ``activity_responses`` table mirrors ``api/activities.py::
get_activity_results`` (the privileged app connection sees every submission).
"""
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivityResponse
from app.models.course import Enrollment
from app.models.quiz import Quiz, QuizAttempt
from app.models.score import ScoreCategory
from app.models.user import User

# The bucket key for artifacts with no ``score_category_id``.
_UNCATEGORIZED = "uncategorized"

_TWO_PLACES = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    """Quantize a money-like Decimal to two places (stable JSON serialization)."""
    return value.quantize(_TWO_PLACES)


async def _active_students(
    db: AsyncSession, course_id: uuid.UUID, *, user_ids: list[uuid.UUID] | None
) -> list[tuple[uuid.UUID, str | None, str]]:
    """Active student roster ``(user_id, full_name, email)`` ordered by name.

    Mirrors the attendance/checkpoint roster query (Enrollment ``active`` +
    role ``student``). ``user_ids`` narrows the roster to the caller (student
    route) while preserving the active-only guarantee.
    """
    stmt = (
        select(Enrollment.user_id, User.full_name, User.email)
        .join(User, User.id == Enrollment.user_id)
        .where(
            Enrollment.course_id == course_id,
            Enrollment.status == "active",
            Enrollment.role == "student",
        )
        .order_by(User.full_name, User.email)
    )
    if user_ids is not None:
        stmt = stmt.where(Enrollment.user_id.in_(user_ids))
    rows = (await db.execute(stmt)).all()
    return [(r[0], r[1], r[2]) for r in rows]


def _bucket_key(category_id: uuid.UUID | None) -> str:
    return str(category_id) if category_id is not None else _UNCATEGORIZED


async def build_score_records(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
    user_ids: list[uuid.UUID] | None = None,
) -> list[dict]:
    """Return one score record per active student (or per ``user_ids`` subset).

    Each record: ``{user_id, full_name, email, categories: [...]}`` where each
    category is ``{category_id, category_name, weight, points_pool,
    earned_points, possible_points, artifacts: [...]}`` and each artifact is
    ``{kind, artifact_id, title, category_id, points, score_pct, earned_points,
    submitted}``.
    """
    students = await _active_students(db, course_id, user_ids=user_ids)
    if not students:
        return []
    student_ids = [s[0] for s in students]

    categories = (
        await db.execute(
            select(ScoreCategory)
            .where(
                ScoreCategory.course_id == course_id,
                ScoreCategory.deleted_at.is_(None),
            )
            .order_by(ScoreCategory.sort, ScoreCategory.created_at)
        )
    ).scalars().all()
    category_by_id = {c.id: c for c in categories}

    graded_quizzes = (
        await db.execute(
            select(Quiz).where(
                Quiz.course_id == course_id,
                Quiz.assessment_purpose == "graded",
                Quiz.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    scored_activities = (
        await db.execute(
            select(Activity).where(
                Activity.course_id == course_id,
                Activity.score_bearing.is_(True),
                Activity.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    quiz_ids = [q.id for q in graded_quizzes]
    activity_ids = [a.id for a in scored_activities]

    # Best attempt per (user, quiz): the highest score wins (deterministic).
    best_score: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = {}
    if quiz_ids:
        attempts = (
            await db.execute(
                select(
                    QuizAttempt.user_id, QuizAttempt.quiz_id, QuizAttempt.score
                ).where(
                    QuizAttempt.quiz_id.in_(quiz_ids),
                    QuizAttempt.user_id.in_(student_ids),
                    QuizAttempt.score.isnot(None),
                )
            )
        ).all()
        for user_id, qid, score in attempts:
            key = (user_id, qid)
            if key not in best_score or score > best_score[key]:
                best_score[key] = score

    # Which (user, activity) pairs have a submission (participation).
    submitted_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    if activity_ids:
        resp_rows = (
            await db.execute(
                select(ActivityResponse.user_id, ActivityResponse.activity_id).where(
                    ActivityResponse.activity_id.in_(activity_ids),
                    ActivityResponse.user_id.in_(student_ids),
                )
            )
        ).all()
        submitted_pairs = {(uid, aid) for uid, aid in resp_rows}

    records: list[dict] = []
    for user_id, full_name, email in students:
        buckets: dict[str, list[dict]] = {}

        for quiz in graded_quizzes:
            score_pct = best_score.get((user_id, quiz.id))
            points = quiz.points
            if score_pct is not None and points is not None:
                earned = _q(points * score_pct / Decimal("100"))
            elif score_pct is not None:
                earned = None
            else:
                earned = _q(Decimal("0")) if points is not None else None
            buckets.setdefault(_bucket_key(quiz.score_category_id), []).append({
                "kind": "quiz",
                "artifact_id": quiz.id,
                "title": quiz.title,
                "category_id": quiz.score_category_id,
                "points": points,
                "score_pct": score_pct,
                "earned_points": earned,
                "submitted": score_pct is not None,
            })

        for activity in scored_activities:
            submitted = (user_id, activity.id) in submitted_pairs
            points = activity.points
            if points is not None:
                earned = _q(points) if submitted else _q(Decimal("0"))
            else:
                earned = None
            buckets.setdefault(_bucket_key(activity.score_category_id), []).append({
                "kind": "activity",
                "artifact_id": activity.id,
                "title": activity.title,
                "category_id": activity.score_category_id,
                "points": points,
                # Participation-only: no correctness percentage.
                "score_pct": None,
                "earned_points": earned,
                "submitted": submitted,
            })

        categories_out: list[dict] = []
        # Emit configured categories first (sorted), then the uncategorized bucket.
        ordered_keys = [str(c.id) for c in categories if str(c.id) in buckets]
        if _UNCATEGORIZED in buckets:
            ordered_keys.append(_UNCATEGORIZED)
        for key in ordered_keys:
            artifacts = buckets[key]
            cat = None
            cat_id = None
            if key != _UNCATEGORIZED:
                cat_id = uuid.UUID(key)
                cat = category_by_id.get(cat_id)
            earned_total = sum(
                (a["earned_points"] or Decimal("0")) for a in artifacts
            )
            possible_total = sum(
                (a["points"] or Decimal("0")) for a in artifacts
            )
            categories_out.append({
                "category_id": cat_id,
                "category_name": cat.name if cat else None,
                "weight": cat.weight if cat else None,
                "points_pool": cat.points_pool if cat else None,
                "earned_points": _q(Decimal(earned_total)),
                "possible_points": _q(Decimal(possible_total)),
                "artifacts": artifacts,
            })

        records.append({
            "user_id": user_id,
            "full_name": full_name,
            "email": email,
            "categories": categories_out,
        })
    return records
