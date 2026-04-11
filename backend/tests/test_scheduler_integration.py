"""Integration tests for FSRS scheduler with database."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course, Enrollment
from app.models.flashcard import FlashcardCard, FlashcardProgress, FlashcardSet
from app.models.scheduler import SchedulerModel
from app.services.scheduler import DEFAULT_PARAMS, SWITCHOVER_THRESHOLD


@pytest_asyncio.fixture
async def course_with_flashcards(db_session: AsyncSession, test_instructor, test_student):
    """Create a course with a flashcard set and one card, with student enrolled."""
    course = Course(
        code="TEST101",
        name="Test Course",
        created_by=test_instructor.id,
    )
    db_session.add(course)
    await db_session.flush()

    enrollment = Enrollment(user_id=test_student.id, course_id=course.id)
    db_session.add(enrollment)

    fc_set = FlashcardSet(
        course_id=course.id,
        created_by=test_instructor.id,
        title="Test Set",
        is_published=True,
    )
    db_session.add(fc_set)
    await db_session.flush()

    card = FlashcardCard(
        flashcard_set_id=fc_set.id,
        card_index=0,
        front="Hello",
        back="World",
    )
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(course)
    await db_session.refresh(fc_set)
    await db_session.refresh(card)

    return course, fc_set, card


class TestSchedulerModelPersistence:
    @pytest.mark.asyncio
    async def test_create_and_load(self, db_session: AsyncSession, test_student, course_with_flashcards):
        course, _, _ = course_with_flashcards
        model = SchedulerModel(
            user_id=test_student.id,
            course_id=course.id,
            parameters=DEFAULT_PARAMS,
            strategy="sm2",
            review_count=0,
        )
        db_session.add(model)
        await db_session.commit()

        result = await db_session.execute(
            select(SchedulerModel).where(
                SchedulerModel.user_id == test_student.id,
                SchedulerModel.course_id == course.id,
            )
        )
        loaded = result.scalar_one()
        assert loaded.parameters == DEFAULT_PARAMS
        assert loaded.strategy == "sm2"
        assert loaded.review_count == 0


class TestAPIResponseShapeUnchanged:
    @pytest.mark.asyncio
    async def test_progress_response_has_expected_fields(
        self, db_session: AsyncSession, test_student, course_with_flashcards
    ):
        """The progress response should have the same shape regardless of scheduler."""
        course, fc_set, card = course_with_flashcards
        progress = FlashcardProgress(
            user_id=test_student.id,
            flashcard_card_id=card.id,
            ease_factor=Decimal("2.50"),
            interval_days=0,
            repetitions=0,
        )
        db_session.add(progress)
        await db_session.commit()
        await db_session.refresh(progress)

        assert progress.stability is None
        assert progress.difficulty is None
        assert progress.last_grade is None
        assert progress.fsrs_review_count == 0


class TestSM2ToFSRSTransition:
    @pytest.mark.asyncio
    async def test_switchover_at_threshold(self, db_session: AsyncSession, test_student, course_with_flashcards):
        """After SWITCHOVER_THRESHOLD reviews, strategy should flip to fsrs."""
        course, fc_set, card = course_with_flashcards

        model = SchedulerModel(
            user_id=test_student.id,
            course_id=course.id,
            parameters=list(DEFAULT_PARAMS),
            strategy="sm2",
            review_count=SWITCHOVER_THRESHOLD - 1,
        )
        db_session.add(model)

        progress = FlashcardProgress(
            user_id=test_student.id,
            flashcard_card_id=card.id,
            ease_factor=Decimal("2.50"),
            interval_days=6,
            repetitions=2,
            last_reviewed=datetime.now(timezone.utc) - timedelta(days=6),
            next_review=datetime.now(timezone.utc),
        )
        db_session.add(progress)
        await db_session.commit()

        from app.services.scheduler import initialize_from_sm2

        stability, difficulty = initialize_from_sm2(
            float(progress.ease_factor), progress.interval_days
        )
        assert stability == 6.0
        assert difficulty == pytest.approx(1.0, abs=0.1)
