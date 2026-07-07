"""P5 B7 — per-type grading + shape validation.

`grade_question(question, answer)` returns 1.0 / 0.0 for each renderer, and
`validate_question_shape(type, options, correct_answer)` rejects malformed
new-type payloads at create/update. `submit_attempt` routes every answered
question through `grade_question` so the mastery `outcome` is correct per type,
while `multiple_choice` behaviour stays byte-identical to today.

Decision 2: `Question.type` is a free String(30) (NO enum widening); the new
types reuse `options` (JSON) + `correct_answer` (String NOT NULL, holding a
JSON-encoded key) with NO migration.
"""
import json
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User
from app.models.quiz import Question, Quiz
from app.models.task import Task
from app.services.question_grading import grade_question, validate_question_shape


def _q(qtype: str, correct_answer, options=None):
    return SimpleNamespace(type=qtype, correct_answer=correct_answer, options=options)


# --------------------------------------------------------------------------- #
#  grade_question — multiple_choice (UNCHANGED)                                #
# --------------------------------------------------------------------------- #


def test_grade_multiple_choice_correct():
    assert grade_question(_q("multiple_choice", "b"), "b") == 1.0


def test_grade_multiple_choice_incorrect():
    assert grade_question(_q("multiple_choice", "b"), "a") == 0.0


def test_grade_multiple_choice_empty_answer():
    # Mirrors the old `selected == correct_answer` on an unanswered question.
    assert grade_question(_q("multiple_choice", "b"), "") == 0.0


# --------------------------------------------------------------------------- #
#  grade_question — matching (answer map == decoded correct_answer map)        #
# --------------------------------------------------------------------------- #


def test_grade_matching_correct_json_string_answer():
    correct = json.dumps({"a": "1", "b": "2", "c": "3"})
    answer = json.dumps({"c": "3", "a": "1", "b": "2"})  # order-independent
    assert grade_question(_q("matching", correct), answer) == 1.0


def test_grade_matching_correct_native_dict_answer():
    correct = json.dumps({"a": "1", "b": "2"})
    assert grade_question(_q("matching", correct), {"a": "1", "b": "2"}) == 1.0


def test_grade_matching_incorrect():
    correct = json.dumps({"a": "1", "b": "2"})
    answer = json.dumps({"a": "2", "b": "1"})
    assert grade_question(_q("matching", correct), answer) == 0.0


def test_grade_matching_malformed_answer_is_zero():
    correct = json.dumps({"a": "1"})
    assert grade_question(_q("matching", correct), "not-json") == 0.0


# --------------------------------------------------------------------------- #
#  grade_question — ordering (answer list == decoded ordered id list)          #
# --------------------------------------------------------------------------- #


def test_grade_ordering_correct():
    correct = json.dumps(["x", "y", "z"])
    assert grade_question(_q("ordering", correct), json.dumps(["x", "y", "z"])) == 1.0


def test_grade_ordering_wrong_order():
    correct = json.dumps(["x", "y", "z"])
    assert grade_question(_q("ordering", correct), json.dumps(["y", "x", "z"])) == 0.0


def test_grade_ordering_native_list_answer():
    correct = json.dumps(["x", "y"])
    assert grade_question(_q("ordering", correct), ["x", "y"]) == 1.0


# --------------------------------------------------------------------------- #
#  grade_question — short_answer (normalized exact match: trim + casefold)     #
# --------------------------------------------------------------------------- #


def test_grade_short_answer_exact():
    assert grade_question(_q("short_answer", json.dumps("Paris")), "Paris") == 1.0


def test_grade_short_answer_normalized_trim_casefold():
    assert grade_question(_q("short_answer", json.dumps("Paris")), "  paRIS  ") == 1.0


def test_grade_short_answer_wrong():
    assert grade_question(_q("short_answer", json.dumps("Paris")), "London") == 0.0


def test_grade_short_answer_tolerates_plain_stored_string():
    # A non-JSON stored correct_answer still grades (defensive fallback).
    assert grade_question(_q("short_answer", "Paris"), "paris") == 1.0


# --------------------------------------------------------------------------- #
#  validate_question_shape — malformed new-type payloads rejected              #
# --------------------------------------------------------------------------- #


def test_validate_matching_rejects_non_object_correct_answer():
    with pytest.raises(HTTPException) as exc:
        validate_question_shape("matching", {"left": ["a"]}, "not-json")
    assert exc.value.status_code in (400, 422)


def test_validate_ordering_rejects_non_list_correct_answer():
    with pytest.raises(HTTPException) as exc:
        validate_question_shape("ordering", ["a", "b"], json.dumps({"a": 1}))
    assert exc.value.status_code in (400, 422)


def test_validate_short_answer_rejects_empty():
    with pytest.raises(HTTPException):
        validate_question_shape("short_answer", None, json.dumps(""))


def test_validate_matching_accepts_valid():
    # No raise on a well-formed matching payload.
    validate_question_shape(
        "matching",
        {"left": ["a", "b"], "right": ["1", "2"]},
        json.dumps({"a": "1", "b": "2"}),
    )


def test_validate_multiple_choice_rejects_answer_outside_options():
    with pytest.raises(HTTPException):
        validate_question_shape("multiple_choice", {"a": "x", "b": "y"}, "z")


def test_validate_rejects_unknown_type():
    with pytest.raises(HTTPException):
        validate_question_shape("mystery", None, "whatever")


# --------------------------------------------------------------------------- #
#  API: shape guard at create / update                                        #
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Grade Question Test",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="GQ000001",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _make_quiz(db_session, course, created_by, **kwargs) -> Quiz:
    quiz = Quiz(
        course_id=course.id,
        created_by=created_by,
        title="GQ quiz",
        **kwargs,
    )
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)
    return quiz


@pytest.mark.asyncio
async def test_add_question_rejects_malformed_matching(
    async_client, db_session, owned_course, logged_in_user
):
    quiz = await _make_quiz(db_session, owned_course, logged_in_user.id)
    r = await async_client.post(
        f"/api/quizzes/{quiz.id}/questions",
        json={
            "question_text": "Match them",
            "type": "matching",
            "options": {"left": ["a"], "right": ["1"]},
            "correct_answer": "not-json",  # malformed → rejected
        },
    )
    assert r.status_code in (400, 422), r.text


@pytest.mark.asyncio
async def test_add_question_accepts_valid_matching(
    async_client, db_session, owned_course, logged_in_user
):
    quiz = await _make_quiz(db_session, owned_course, logged_in_user.id)
    r = await async_client.post(
        f"/api/quizzes/{quiz.id}/questions",
        json={
            "question_text": "Match them",
            "type": "matching",
            "options": {"left": ["a", "b"], "right": ["1", "2"]},
            "correct_answer": json.dumps({"a": "1", "b": "2"}),
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["type"] == "matching"


@pytest.mark.asyncio
async def test_update_question_rejects_malformed_ordering(
    async_client, db_session, owned_course, logged_in_user
):
    quiz = await _make_quiz(db_session, owned_course, logged_in_user.id)
    q = Question(
        quiz_id=quiz.id,
        question_index=0,
        type="multiple_choice",
        question_text="Q",
        options={"a": "x", "b": "y"},
        correct_answer="a",
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)

    r = await async_client.patch(
        f"/api/questions/{q.id}",
        json={"type": "ordering", "correct_answer": json.dumps({"not": "a-list"})},
    )
    assert r.status_code in (400, 422), r.text


# --------------------------------------------------------------------------- #
#  API: submit_attempt routes each type through grade_question                 #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_submit_attempt_grades_short_answer_normalized(
    async_client, db_session, owned_course, logged_in_user
):
    """A short_answer question is graded via grade_question (trim + casefold),
    and the enqueued mastery Task carries outcome=1.0."""
    quiz = await _make_quiz(
        db_session, owned_course, logged_in_user.id,
        assessment_purpose="practice", is_published=False,
    )
    q = Question(
        quiz_id=quiz.id,
        question_index=0,
        type="short_answer",
        question_text="Capital of France?",
        options=None,
        correct_answer=json.dumps("Paris"),
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)

    r = await async_client.post(
        f"/api/quizzes/{quiz.id}/attempt",
        json={"answers": {str(q.id): "  paris "}},
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()["data"]
    assert data["correct_count"] == 1
    assert data["results"][0]["is_correct"] is True

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    outcomes = [t.payload["outcome"] for t in tasks if t.payload["target_id"] == str(q.id)]
    assert outcomes == [1.0]


@pytest.mark.asyncio
async def test_submit_attempt_multiple_choice_identical(
    async_client, db_session, owned_course, logged_in_user
):
    """MC scoring/mastery stays byte-identical: correct key → 1.0, wrong → 0.0."""
    quiz = await _make_quiz(
        db_session, owned_course, logged_in_user.id,
        assessment_purpose="practice", is_published=False,
    )
    q_ok = Question(
        quiz_id=quiz.id, question_index=0, type="multiple_choice",
        question_text="2+2?", options={"a": "3", "b": "4"}, correct_answer="b",
    )
    q_bad = Question(
        quiz_id=quiz.id, question_index=1, type="multiple_choice",
        question_text="Sky?", options={"a": "blue", "b": "green"}, correct_answer="a",
    )
    db_session.add_all([q_ok, q_bad])
    await db_session.commit()
    await db_session.refresh(q_ok)
    await db_session.refresh(q_bad)

    r = await async_client.post(
        f"/api/quizzes/{quiz.id}/attempt",
        json={"answers": {str(q_ok.id): "b", str(q_bad.id): "b"}},
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()["data"]
    assert data["correct_count"] == 1

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    by_target = {t.payload["target_id"]: t.payload["outcome"] for t in tasks}
    assert by_target[str(q_ok.id)] == 1.0
    assert by_target[str(q_bad.id)] == 0.0
