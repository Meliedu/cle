"""Cross-instructor ownership isolation tests for per-item review endpoints.

Each test seeds two instructors plus a course owned by instructor A. The
authenticated client is instructor B (`logged_in_user`). All edit/delete/
regenerate calls against A's items must return 404, never 200, never 403
(the handlers deliberately return 404 to avoid leaking the existence of
other instructors' rows).
"""

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.course import Course, Enrollment
from app.models.flashcard import FlashcardCard, FlashcardSet
from app.models.pronunciation import (
    PronunciationItem,
    PronunciationSet,
)
from app.models.quiz import Question, Quiz
from app.models.user import User


@pytest_asyncio.fixture
async def instructor_a(db_session: AsyncSession) -> User:
    user = User(
        better_auth_id="dev_instr_a",
        email="instr-a@ust.hk",
        full_name="Instructor A",
        role="instructor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def instructor_b(db_session: AsyncSession) -> User:
    user = User(
        better_auth_id="dev_instr_b",
        email="instr-b@ust.hk",
        full_name="Instructor B",
        role="instructor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def shared_course(
    db_session: AsyncSession, instructor_a: User, instructor_b: User
) -> Course:
    """A course owned by instructor A. Both instructors are enrolled so the
    `verify_enrollment` gate passes — the only thing keeping B out of A's
    items is the `created_by == user.id` check on each per-item handler."""
    course = Course(
        name="Phonetics",
        code="LING220",
        language="english",
        instructor_id=instructor_a.id,
        enroll_code="OWNTEST1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=instructor_a.id, role="instructor")
    )
    db_session.add(
        Enrollment(course_id=course.id, user_id=instructor_b.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest_asyncio.fixture
async def client_as_b(
    db_session: AsyncSession, instructor_b: User
) -> AsyncIterator[AsyncClient]:
    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return instructor_b

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Quiz: PATCH/DELETE/regenerate /questions/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quiz_question_edit_blocked_for_non_owner(
    db_session, shared_course, instructor_a, client_as_b
):
    quiz = Quiz(
        course_id=shared_course.id,
        created_by=instructor_a.id,
        title="A's Quiz",
        quiz_type="multiple_choice",
    )
    db_session.add(quiz)
    await db_session.flush()
    question = Question(
        quiz_id=quiz.id,
        question_index=0,
        type="multiple_choice",
        question_text="What?",
        options={"A": "x", "B": "y", "C": "z", "D": "w"},
        correct_answer="A",
        explanation="",
        difficulty="medium",
    )
    db_session.add(question)
    await db_session.commit()

    resp = await client_as_b.patch(
        f"/api/questions/{question.id}",
        json={"question_text": "B's tampered question"},
    )
    assert resp.status_code == 404

    # And the row is unchanged.
    await db_session.refresh(question)
    assert question.question_text == "What?"


@pytest.mark.asyncio
async def test_quiz_question_delete_blocked_for_non_owner(
    db_session, shared_course, instructor_a, client_as_b
):
    quiz = Quiz(
        course_id=shared_course.id,
        created_by=instructor_a.id,
        title="A's Quiz",
        quiz_type="multiple_choice",
    )
    db_session.add(quiz)
    await db_session.flush()
    question = Question(
        quiz_id=quiz.id,
        question_index=0,
        type="multiple_choice",
        question_text="Q",
        options={"A": "x", "B": "y", "C": "z", "D": "w"},
        correct_answer="A",
        explanation="",
        difficulty="medium",
    )
    db_session.add(question)
    await db_session.commit()

    resp = await client_as_b.delete(f"/api/questions/{question.id}")
    assert resp.status_code == 404

    # Row still present.
    await db_session.refresh(question)
    assert question.question_text == "Q"


# ---------------------------------------------------------------------------
# Flashcard: POST /flashcard-sets/{id}/cards, PATCH/DELETE/regenerate
# /flashcard-cards/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flashcard_add_card_blocked_for_non_owner(
    db_session, shared_course, instructor_a, client_as_b
):
    fc_set = FlashcardSet(
        course_id=shared_course.id,
        created_by=instructor_a.id,
        title="A's Set",
        is_published=False,
    )
    db_session.add(fc_set)
    await db_session.commit()

    resp = await client_as_b.post(
        f"/api/flashcard-sets/{fc_set.id}/cards",
        json={"front": "tampered", "back": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_flashcard_card_edit_blocked_for_non_owner(
    db_session, shared_course, instructor_a, client_as_b
):
    fc_set = FlashcardSet(
        course_id=shared_course.id,
        created_by=instructor_a.id,
        title="A's Set",
        is_published=False,
    )
    db_session.add(fc_set)
    await db_session.flush()
    card = FlashcardCard(
        flashcard_set_id=fc_set.id,
        card_index=0,
        front="original front",
        back="original back",
        difficulty="medium",
    )
    db_session.add(card)
    await db_session.commit()

    resp = await client_as_b.patch(
        f"/api/flashcard-cards/{card.id}",
        json={"front": "tampered"},
    )
    assert resp.status_code == 404

    await db_session.refresh(card)
    assert card.front == "original front"


@pytest.mark.asyncio
async def test_flashcard_card_delete_blocked_for_non_owner(
    db_session, shared_course, instructor_a, client_as_b
):
    fc_set = FlashcardSet(
        course_id=shared_course.id,
        created_by=instructor_a.id,
        title="A's Set",
        is_published=False,
    )
    db_session.add(fc_set)
    await db_session.flush()
    card = FlashcardCard(
        flashcard_set_id=fc_set.id,
        card_index=0,
        front="f",
        back="b",
        difficulty="medium",
    )
    db_session.add(card)
    await db_session.commit()

    resp = await client_as_b.delete(f"/api/flashcard-cards/{card.id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Pronunciation: POST /pronunciation-sets/{id}/items, PATCH/DELETE/regenerate
# /pronunciation-items/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pronunciation_add_item_blocked_for_non_owner(
    db_session, shared_course, instructor_a, client_as_b
):
    pron_set = PronunciationSet(
        course_id=shared_course.id,
        created_by=instructor_a.id,
        title="A's Pron Set",
        is_published=False,
        difficulty="medium",
        language="english",
    )
    db_session.add(pron_set)
    await db_session.commit()

    resp = await client_as_b.post(
        f"/api/pronunciation-sets/{pron_set.id}/items",
        json={"text": "tampered", "item_type": "word"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pronunciation_item_edit_blocked_for_non_owner(
    db_session, shared_course, instructor_a, client_as_b
):
    pron_set = PronunciationSet(
        course_id=shared_course.id,
        created_by=instructor_a.id,
        title="A's Pron Set",
        is_published=False,
        difficulty="medium",
        language="english",
    )
    db_session.add(pron_set)
    await db_session.flush()
    item = PronunciationItem(
        pronunciation_set_id=pron_set.id,
        item_index=0,
        text="original",
        item_type="word",
        difficulty="medium",
    )
    db_session.add(item)
    await db_session.commit()

    resp = await client_as_b.patch(
        f"/api/pronunciation-items/{item.id}",
        json={"text": "tampered"},
    )
    assert resp.status_code == 404

    await db_session.refresh(item)
    assert item.text == "original"


@pytest.mark.asyncio
async def test_pronunciation_item_delete_blocked_for_non_owner(
    db_session, shared_course, instructor_a, client_as_b
):
    pron_set = PronunciationSet(
        course_id=shared_course.id,
        created_by=instructor_a.id,
        title="A's Pron Set",
        is_published=False,
        difficulty="medium",
        language="english",
    )
    db_session.add(pron_set)
    await db_session.flush()
    item = PronunciationItem(
        pronunciation_set_id=pron_set.id,
        item_index=0,
        text="word",
        item_type="word",
        difficulty="medium",
    )
    db_session.add(item)
    await db_session.commit()

    resp = await client_as_b.delete(f"/api/pronunciation-items/{item.id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Schema-level guards (regression tests for the review feedback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pronunciation_create_rejects_invalid_difficulty(
    db_session, shared_course, instructor_b, client_as_b
):
    """Owner-side guard: invalid difficulty enum is rejected at the schema
    layer rather than silently stored. Regression for review issue #1."""
    pron_set = PronunciationSet(
        course_id=shared_course.id,
        created_by=instructor_b.id,
        title="B's set",
        is_published=False,
        difficulty="medium",
        language="english",
    )
    db_session.add(pron_set)
    await db_session.commit()

    resp = await client_as_b.post(
        f"/api/pronunciation-sets/{pron_set.id}/items",
        json={"text": "hello", "item_type": "word", "difficulty": "mixed"},
    )
    # Pydantic Literal -> 422 Unprocessable Entity.
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_quiz_question_create_rejects_correct_answer_outside_options(
    db_session, shared_course, instructor_b, client_as_b
):
    """The new model_validator on QuestionCreate must reject an answer that
    isn't a key in the options dict. Regression for review issue #2."""
    quiz = Quiz(
        course_id=shared_course.id,
        created_by=instructor_b.id,
        title="B's quiz",
        quiz_type="multiple_choice",
    )
    db_session.add(quiz)
    await db_session.commit()

    resp = await client_as_b.post(
        f"/api/quizzes/{quiz.id}/questions",
        json={
            "question_text": "?",
            "options": {"A": "x", "B": "y", "C": "z", "D": "w"},
            "correct_answer": "E",
        },
    )
    assert resp.status_code == 422
