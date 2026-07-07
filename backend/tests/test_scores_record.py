"""P5 B11: teacher/student score record aggregation (`scores.py` extension).

`GET /courses/{id}/scores` (owner-guarded) returns each ACTIVE student's
per-category / per-artifact rollup from GRADED quiz attempts + SCORE-BEARING
activity responses. `GET /users/me/courses/{id}/scores` (enrollment-scoped,
active-only) returns ONLY the caller's own record (S059). A student calling the
teacher route → 403; a non-owner teacher → 404.

Mirrors ``test_score_categories_api.py`` for the fixture + guard idioms.
"""
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, Enrollment, User
from app.models.activity import Activity, ActivityResponse
from app.models.quiz import Quiz, QuizAttempt
from app.models.score import ScoreCategory


@pytest_asyncio.fixture
async def scored_course(db_session: AsyncSession, logged_in_user: User) -> dict:
    """A course owned by ``logged_in_user`` with:

    * an active student (``student``) and an active-but-empty second student
      (``student2``);
    * a GRADED score-bearing quiz in category "Quizzes" (student scored 80%);
    * a SCORE-BEARING activity in category "Participation" (student responded);
    * a PRACTICE quiz + a non-score-bearing activity that must NOT appear.
    """
    course = Course(
        name="Scored", language="english",
        instructor_id=logged_in_user.id, enroll_code="RECORD01",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )

    student = User(
        better_auth_id="rec_student_01", email="recstudent@connect.ust.hk",
        full_name="Rec Student", role="student",
    )
    student2 = User(
        better_auth_id="rec_student_02", email="recstudent2@connect.ust.hk",
        full_name="Rec Student Two", role="student",
    )
    db_session.add_all([student, student2])
    await db_session.flush()
    db_session.add_all([
        Enrollment(course_id=course.id, user_id=student.id, role="student", status="active"),
        Enrollment(course_id=course.id, user_id=student2.id, role="student", status="active"),
    ])

    quizzes_cat = ScoreCategory(course_id=course.id, name="Quizzes", weight=Decimal("40"), sort=1)
    part_cat = ScoreCategory(course_id=course.id, name="Participation", weight=Decimal("10"), sort=0)
    db_session.add_all([quizzes_cat, part_cat])
    await db_session.flush()

    graded_quiz = Quiz(
        course_id=course.id, created_by=logged_in_user.id, title="Midterm Quiz",
        assessment_purpose="graded", score_bearing=True,
        score_category_id=quizzes_cat.id, points=Decimal("100"),
    )
    practice_quiz = Quiz(
        course_id=course.id, created_by=logged_in_user.id, title="Warmup",
        assessment_purpose="practice", score_bearing=False,
    )
    db_session.add_all([graded_quiz, practice_quiz])
    await db_session.flush()

    # Student scored 80% on the graded quiz; also has a practice attempt (ignored).
    db_session.add(QuizAttempt(
        quiz_id=graded_quiz.id, user_id=student.id, answers={"0": "a"},
        score=Decimal("80.00"), total_questions=5, correct_count=4,
    ))
    db_session.add(QuizAttempt(
        quiz_id=practice_quiz.id, user_id=student.id, answers={"0": "a"},
        score=Decimal("10.00"), total_questions=5, correct_count=1,
    ))

    scored_activity = Activity(
        course_id=course.id, format="vote", title="Class Poll",
        status="published", score_bearing=True,
        score_category_id=part_cat.id, points=Decimal("5"),
    )
    unscored_activity = Activity(
        course_id=course.id, format="swipe", title="Fun Swipe",
        status="published", score_bearing=False,
    )
    db_session.add_all([scored_activity, unscored_activity])
    await db_session.flush()
    db_session.add(ActivityResponse(
        activity_id=scored_activity.id, user_id=student.id,
        payload={"choice": "yes"}, status="on_time",
    ))
    db_session.add(ActivityResponse(
        activity_id=unscored_activity.id, user_id=student.id,
        payload={"dir": "right"}, status="on_time",
    ))
    await db_session.commit()
    await db_session.refresh(course)
    return {
        "course": course, "student": student, "student2": student2,
        "graded_quiz": graded_quiz, "scored_activity": scored_activity,
        "quizzes_cat": quizzes_cat, "part_cat": part_cat,
    }


def _find_record(records: list[dict], user_id) -> dict:
    return next(r for r in records if r["user_id"] == str(user_id))


# ----- teacher /scores -----

@pytest.mark.asyncio
async def test_teacher_scores_rollup_active_students(
    async_client: AsyncClient, scored_course: dict
):
    course = scored_course["course"]
    r = await async_client.get(f"/api/courses/{course.id}/scores")
    assert r.status_code == 200
    records = r.json()["data"]
    # Both active students appear (student2 with an empty record); instructor excluded.
    user_ids = {rec["user_id"] for rec in records}
    assert str(scored_course["student"].id) in user_ids
    assert str(scored_course["student2"].id) in user_ids
    assert len(records) == 2

    rec = _find_record(records, scored_course["student"].id)
    cats_by_name = {c["category_name"]: c for c in rec["categories"]}
    assert "Quizzes" in cats_by_name and "Participation" in cats_by_name

    quizzes = cats_by_name["Quizzes"]
    quiz_artifacts = {a["title"]: a for a in quizzes["artifacts"]}
    assert "Midterm Quiz" in quiz_artifacts
    assert quiz_artifacts["Midterm Quiz"]["kind"] == "quiz"
    assert float(quiz_artifacts["Midterm Quiz"]["score_pct"]) == 80.0
    # 80% of 100 points.
    assert float(quiz_artifacts["Midterm Quiz"]["earned_points"]) == 80.0
    # Practice quiz is NOT in any category.
    assert "Warmup" not in quiz_artifacts

    part = cats_by_name["Participation"]
    part_artifacts = {a["title"]: a for a in part["artifacts"]}
    assert "Class Poll" in part_artifacts
    assert part_artifacts["Class Poll"]["kind"] == "activity"
    assert part_artifacts["Class Poll"]["submitted"] is True
    # Participation-only: full points on submit.
    assert float(part_artifacts["Class Poll"]["earned_points"]) == 5.0
    # Non-score-bearing activity excluded.
    assert "Fun Swipe" not in part_artifacts


@pytest.mark.asyncio
async def test_teacher_scores_empty_student_record(
    async_client: AsyncClient, scored_course: dict
):
    course = scored_course["course"]
    r = await async_client.get(f"/api/courses/{course.id}/scores")
    records = r.json()["data"]
    rec = _find_record(records, scored_course["student2"].id)
    # student2 has no attempts/responses → artifacts present but unearned.
    for cat in rec["categories"]:
        for art in cat["artifacts"]:
            assert art["submitted"] is False
            assert float(art["earned_points"] or 0) == 0.0


@pytest.mark.asyncio
async def test_teacher_scores_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="rec_other_instr", email="recother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="RECFOR01",
    )
    db_session.add(course)
    await db_session.commit()
    r = await async_client.get(f"/api/courses/{course.id}/scores")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_student_forbidden_on_teacher_scores(
    db_session: AsyncSession, scored_course: dict
):
    student = scored_course["student"]
    course = scored_course["course"]

    async def override_db():
        yield db_session

    async def override_user():
        return student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.get(f"/api/courses/{course.id}/scores")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ----- student /users/me/courses/{id}/scores -----

@pytest.mark.asyncio
async def test_student_sees_only_own_record(
    db_session: AsyncSession, scored_course: dict
):
    student = scored_course["student"]
    course = scored_course["course"]

    async def override_db():
        yield db_session

    async def override_user():
        return student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.get(f"/api/users/me/courses/{course.id}/scores")
            assert r.status_code == 200
            rec = r.json()["data"]
            # Single record, and it is the caller's own.
            assert rec["user_id"] == str(student.id)
            cats = {c["category_name"]: c for c in rec["categories"]}
            quiz_art = {a["title"]: a for a in cats["Quizzes"]["artifacts"]}
            assert float(quiz_art["Midterm Quiz"]["score_pct"]) == 80.0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_not_enrolled_forbidden(
    db_session: AsyncSession, scored_course: dict
):
    course = scored_course["course"]
    outsider = User(
        better_auth_id="rec_outsider_01", email="recoutsider@connect.ust.hk",
        full_name="Outsider", role="student",
    )
    db_session.add(outsider)
    await db_session.commit()

    async def override_db():
        yield db_session

    async def override_user():
        return outsider

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.get(f"/api/users/me/courses/{course.id}/scores")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
