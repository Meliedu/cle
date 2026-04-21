"""Integration tests for `GET /quizzes/{quiz_id}/active-session`.

Covers:
- no session → active=False
- waiting session → active=True, status="waiting"
- finished session → active=False
- missing quiz → 404
"""

from datetime import datetime, timezone

import pytest

from app.models.course import Course, Enrollment
from app.models.quiz import Quiz
from app.models.session import LiveSession


@pytest.mark.asyncio
async def test_active_session_false_when_none_exists(
    async_client, logged_in_user, db_session
):
    course = Course(
        name="Test Course",
        code="TC101",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="ACTIVE01",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=logged_in_user.id, role="instructor"
        )
    )
    quiz = Quiz(
        course_id=course.id,
        created_by=logged_in_user.id,
        title="Q",
        quiz_type="multiple_choice",
        purpose="live",
    )
    db_session.add(quiz)
    await db_session.commit()

    resp = await async_client.get(f"/api/quizzes/{quiz.id}/active-session")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["active"] is False
    assert body["data"]["session_id"] is None


@pytest.mark.asyncio
async def test_active_session_true_when_waiting(
    async_client, logged_in_user, db_session
):
    course = Course(
        name="C",
        code="C102",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="ACTIVE02",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=logged_in_user.id, role="instructor"
        )
    )
    quiz = Quiz(
        course_id=course.id,
        created_by=logged_in_user.id,
        title="Q",
        quiz_type="multiple_choice",
        purpose="live",
    )
    db_session.add(quiz)
    await db_session.flush()
    session = LiveSession(
        quiz_id=quiz.id,
        course_id=course.id,
        host_id=logged_in_user.id,
        join_code="AAAAAA",
        status="waiting",
    )
    db_session.add(session)
    await db_session.commit()

    resp = await async_client.get(f"/api/quizzes/{quiz.id}/active-session")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["active"] is True
    assert data["status"] == "waiting"
    assert data["session_id"] == str(session.id)


@pytest.mark.asyncio
async def test_active_session_false_when_finished(
    async_client, logged_in_user, db_session
):
    course = Course(
        name="C",
        code="C103",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="ACTIVE03",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=logged_in_user.id, role="instructor"
        )
    )
    quiz = Quiz(
        course_id=course.id,
        created_by=logged_in_user.id,
        title="Q",
        quiz_type="multiple_choice",
        purpose="live",
    )
    db_session.add(quiz)
    await db_session.flush()
    db_session.add(
        LiveSession(
            quiz_id=quiz.id,
            course_id=course.id,
            host_id=logged_in_user.id,
            join_code="BBBBBB",
            status="finished",
            ended_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    resp = await async_client.get(f"/api/quizzes/{quiz.id}/active-session")
    assert resp.status_code == 200
    assert resp.json()["data"]["active"] is False


@pytest.mark.asyncio
async def test_active_session_404_for_missing_quiz(async_client):
    import uuid

    missing = uuid.uuid4()
    resp = await async_client.get(f"/api/quizzes/{missing}/active-session")
    assert resp.status_code == 404
