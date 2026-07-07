"""Model/constraint tests for ``checkpoint_responses`` (P3 Task 2).

``checkpoint_responses`` is a student-owned row table (Decision 2). Its RLS
owner-isolation policy is proven separately under ``meli_app`` in Task 14; here
we cover only the ORM columns, defaults and CHECK/UNIQUE constraints via
``Base.metadata.create_all`` in the disposable test DB (``db_session``).

Owner = ``user_id``. One response row per ``(card_id, user_id)``. ``confidence``
is the −2..+2 scale (nullable — the ``final_comments`` card carries text, not a
confidence value); ``status`` is ``on_time``/``late`` derived from the close time.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from app.models.checkpoint import Checkpoint, CheckpointCard, CheckpointResponse
from app.models.course import Course


@pytest_asyncio.fixture
async def seed_checkpoint(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="RESP" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.flush()
    cp = Checkpoint(course_id=course.id, kind="session", title="Session 1 check")
    db_session.add(cp)
    await db_session.flush()
    card = CheckpointCard(
        checkpoint_id=cp.id, position=0, kind="review_point", prompt="Tone sandhi?"
    )
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(cp)
    await db_session.refresh(card)
    return cp, card


@pytest.mark.asyncio
async def test_response_create_and_defaults(db_session, seed_checkpoint, test_student):
    cp, card = seed_checkpoint
    r = CheckpointResponse(
        checkpoint_id=cp.id,
        card_id=card.id,
        user_id=test_student.id,
        confidence=1,
        status="on_time",
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    assert r.id is not None
    assert r.confidence == 1
    assert r.status == "on_time"
    assert r.text_response is None
    assert r.submitted_at is not None
    assert r.created_at is not None


@pytest.mark.asyncio
async def test_response_confidence_accepts_full_scale_and_null(
    db_session, seed_checkpoint, test_student
):
    cp, _ = seed_checkpoint
    # A NULL confidence (final_comments text response) + every −2..+2 value.
    for idx, confidence in enumerate((None, -2, -1, 0, 1, 2)):
        card = CheckpointCard(
            checkpoint_id=cp.id, position=idx + 1, kind="review_point", prompt=f"q{idx}"
        )
        db_session.add(card)
        await db_session.flush()
        db_session.add(
            CheckpointResponse(
                checkpoint_id=cp.id,
                card_id=card.id,
                user_id=test_student.id,
                confidence=confidence,
                status="on_time",
            )
        )
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [3, -3])
async def test_response_confidence_out_of_range_rejected(
    db_session, seed_checkpoint, test_student, bad
):
    cp, card = seed_checkpoint
    db_session.add(
        CheckpointResponse(
            checkpoint_id=cp.id,
            card_id=card.id,
            user_id=test_student.id,
            confidence=bad,
            status="on_time",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_response_bad_status_rejected(db_session, seed_checkpoint, test_student):
    cp, card = seed_checkpoint
    db_session.add(
        CheckpointResponse(
            checkpoint_id=cp.id,
            card_id=card.id,
            user_id=test_student.id,
            confidence=0,
            status="nonsense",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_response_late_status_accepted(db_session, seed_checkpoint, test_student):
    cp, card = seed_checkpoint
    r = CheckpointResponse(
        checkpoint_id=cp.id,
        card_id=card.id,
        user_id=test_student.id,
        text_response="I get it now",
        status="late",
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    assert r.status == "late"
    assert r.text_response == "I get it now"


@pytest.mark.asyncio
async def test_response_unique_card_user(db_session, seed_checkpoint, test_student):
    cp, card = seed_checkpoint
    db_session.add(
        CheckpointResponse(
            checkpoint_id=cp.id,
            card_id=card.id,
            user_id=test_student.id,
            confidence=1,
            status="on_time",
        )
    )
    await db_session.flush()
    db_session.add(
        CheckpointResponse(
            checkpoint_id=cp.id,
            card_id=card.id,
            user_id=test_student.id,
            confidence=2,
            status="on_time",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
