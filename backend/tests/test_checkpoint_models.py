import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from app.models.checkpoint import Checkpoint, CheckpointCard
from app.models.course import Course
from app.models.score import ScoreCategory


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="CHKP" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_checkpoint_defaults_draft(db_session, seed_course):
    cp = Checkpoint(course_id=seed_course.id, kind="session", title="Session 1 check")
    db_session.add(cp)
    await db_session.commit()
    await db_session.refresh(cp)
    assert cp.status == "draft"
    assert cp.qr_enabled is False


@pytest.mark.asyncio
async def test_checkpoint_status_enum_accepts_all_values(db_session, seed_course):
    # Decision 3: the enum carries the FULL P3 machine so no widening later.
    for status in (
        "draft",
        "teacher_editing",
        "approved",
        "scheduled",
        "published",
        "live",
        "closed",
        "archived",
    ):
        cp = Checkpoint(
            course_id=seed_course.id, kind="session", title=f"c-{status}", status=status
        )
        db_session.add(cp)
        await db_session.commit()
        await db_session.refresh(cp)
        assert cp.status == status


@pytest.mark.asyncio
async def test_checkpoint_bad_status_rejected(db_session, seed_course):
    cp = Checkpoint(
        course_id=seed_course.id, kind="session", title="c", status="nonsense"
    )
    db_session.add(cp)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_checkpoint_bad_kind_rejected(db_session, seed_course):
    cp = Checkpoint(course_id=seed_course.id, kind="oops", title="c")
    db_session.add(cp)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_card_requires_valid_kind(db_session, seed_course):
    cp = Checkpoint(course_id=seed_course.id, kind="session", title="c")
    db_session.add(cp)
    await db_session.flush()
    db_session.add(
        CheckpointCard(
            checkpoint_id=cp.id, position=0, kind="bogus", prompt="Anything?"
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_only_one_final_comments_card(db_session, seed_course):
    cp = Checkpoint(course_id=seed_course.id, kind="session", title="c")
    db_session.add(cp)
    await db_session.flush()
    db_session.add(
        CheckpointCard(
            checkpoint_id=cp.id, position=0, kind="final_comments", prompt="Anything else?"
        )
    )
    db_session.add(
        CheckpointCard(
            checkpoint_id=cp.id, position=1, kind="final_comments", prompt="dup"
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_checkpoint_card_can_target_concept_tag(db_session, seed_course):
    # target_kind='checkpoint_card' must be accepted by the widened CHECK.
    from app.models.concept import Concept, ConceptTag

    concept = Concept(course_id=seed_course.id, name="tone sandhi", status="approved")
    db_session.add(concept)
    await db_session.flush()
    tag = ConceptTag(
        concept_id=concept.id,
        target_kind="checkpoint_card",
        target_id=uuid.uuid4(),
        suggestion_source="inheritance",
    )
    db_session.add(tag)
    await db_session.commit()  # must not raise


@pytest.mark.asyncio
async def test_score_category(db_session, seed_course):
    sc = ScoreCategory(course_id=seed_course.id, name="Participation", sort=0)
    db_session.add(sc)
    await db_session.commit()
    await db_session.refresh(sc)
    assert sc.name == "Participation"
    assert sc.sort == 0
