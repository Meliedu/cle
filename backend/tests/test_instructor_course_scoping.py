"""Instructor-only routes must be scoped to the *course*, not just the role.

``require_instructor`` proves only that the caller is HKUST staff *somewhere*:
it reads ``User.role``, which is derived from the email domain. It says nothing
about the course in the path. Pairing it with ``verify_enrollment`` (which
accepts an active enrollment of ANY role) therefore left a real hole:

an enroll code is shared with a whole class, so it is not a secret from other
staff. ``POST /api/courses/enroll-by-code`` deliberately forces
``role="student"`` on the row it creates, but the caller's *global* role stays
``instructor``. So any ``@ust.hk`` account that learned another instructor's
join code could clear both gates on a course they do not teach, and reach
Canvas roster import (which can drop real students), the quiz answer key, and
the folder trees.

The fix is ``verify_instructor_enrollment``, which additionally requires
``Enrollment.role == "instructor"``. These tests pin that: an outsider who has
self-enrolled by code is refused, and the course's real owner still passes.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.course import Course, Enrollment
from app.models.quiz import Question, Quiz
from app.models.user import User


async def _as(user: User, db_session):
    """An AsyncClient authenticated as ``user``."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        # AuthMiddleware rejects /api/* without a Bearer header before routing,
        # independently of the get_current_user override.
        headers={"Authorization": "Bearer t"},
    )


@pytest.fixture
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


async def _owned_course(db_session, owner: User) -> Course:
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=owner.id,
        enroll_code="OWNR2345",
        context_status="approved",
        setup_status="published",
        enroll_code_active=True,
        join_mode="code",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    # The owner's instructor-role enrollment, exactly as create_course makes it.
    db_session.add(
        Enrollment(
            course_id=course.id,
            user_id=owner.id,
            role="instructor",
            status="active",
        )
    )
    await db_session.commit()
    return course


async def _outsider(db_session) -> User:
    """Another HKUST staff account: global role instructor, not this course's."""
    user = User(
        better_auth_id=f"outsider_{uuid.uuid4().hex[:8]}",
        email=f"outsider_{uuid.uuid4().hex[:6]}@ust.hk",
        full_name="Other Department Staff",
        role="instructor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_self_enrolled_staff_cannot_read_another_courses_answer_key(
    db_session, test_instructor, _clear_overrides
):
    """The exact escalation: join by code, then read the quiz answer key."""
    course = await _owned_course(db_session, test_instructor)
    quiz = Quiz(
        course_id=course.id,
        created_by=test_instructor.id,
        title="Unit 1 check",
        quiz_type="multiple_choice",
    )
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)
    db_session.add(
        Question(
            quiz_id=quiz.id,
            question_index=0,
            type="multiple_choice",
            question_text="你好 means?",
            options=["hello", "goodbye"],
            correct_answer="hello",
        )
    )
    await db_session.commit()

    outsider = await _outsider(db_session)
    # What enroll-by-code grants: an ACTIVE, student-role enrollment.
    db_session.add(
        Enrollment(
            course_id=course.id,
            user_id=outsider.id,
            role="student",
            status="active",
        )
    )
    await db_session.commit()

    async with await _as(outsider, db_session) as client:
        res = await client.get(f"/api/quizzes/{quiz.id}/preview")

    assert res.status_code == 403, res.text
    assert "hello" not in res.text


@pytest.mark.asyncio
async def test_course_owner_can_still_read_the_answer_key(
    db_session, test_instructor, _clear_overrides
):
    """The gate must not lock out the instructor who owns the course."""
    course = await _owned_course(db_session, test_instructor)
    quiz = Quiz(
        course_id=course.id,
        created_by=test_instructor.id,
        title="Unit 1 check",
        quiz_type="multiple_choice",
    )
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)
    db_session.add(
        Question(
            quiz_id=quiz.id,
            question_index=0,
            type="multiple_choice",
            question_text="你好 means?",
            options=["hello", "goodbye"],
            correct_answer="hello",
        )
    )
    await db_session.commit()

    async with await _as(test_instructor, db_session) as client:
        res = await client.get(f"/api/quizzes/{quiz.id}/preview")

    assert res.status_code == 200, res.text
    assert res.json()["data"]["questions"][0]["correct_answer"] == "hello"


@pytest.mark.asyncio
async def test_owner_without_an_enrollment_row_is_not_locked_out(
    db_session, test_instructor, _clear_overrides
):
    """Ownership alone must satisfy the gate.

    `create_course` writes an instructor-role enrollment today, but a course
    predating that (or one whose row was lost) would otherwise leave its real
    owner 403'd out of their own quizzes by the tightened check.
    """
    course = Course(
        name="LANG1599",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="LEGC2345",
        context_status="approved",
        setup_status="published",
        enroll_code_active=True,
        join_mode="code",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    # Deliberately NO enrollment row for the owner.

    quiz = Quiz(
        course_id=course.id,
        created_by=test_instructor.id,
        title="Legacy quiz",
        quiz_type="multiple_choice",
    )
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)

    async with await _as(test_instructor, db_session) as client:
        res = await client.get(f"/api/quizzes/{quiz.id}/preview")

    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_self_enrolled_staff_cannot_import_another_courses_roster(
    db_session, test_instructor, _clear_overrides
):
    """Roster import can DROP real students, the most damaging write path."""
    course = await _owned_course(db_session, test_instructor)
    outsider = await _outsider(db_session)
    db_session.add(
        Enrollment(
            course_id=course.id,
            user_id=outsider.id,
            role="student",
            status="active",
        )
    )
    await db_session.commit()

    async with await _as(outsider, db_session) as client:
        res = await client.post(
            f"/api/courses/{course.id}/canvas/roster/import",
            json={"send_invite_emails": False},
        )

    assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_self_enrolled_staff_cannot_delete_another_courses_quiz_folder(
    db_session, test_instructor, _clear_overrides
):
    course = await _owned_course(db_session, test_instructor)
    outsider = await _outsider(db_session)
    db_session.add(
        Enrollment(
            course_id=course.id,
            user_id=outsider.id,
            role="student",
            status="active",
        )
    )
    await db_session.commit()

    async with await _as(outsider, db_session) as client:
        res = await client.post(
            f"/api/courses/{course.id}/quiz-folders",
            json={"name": "injected"},
        )

    assert res.status_code == 403, res.text
