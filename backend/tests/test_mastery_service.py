import math
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.services.mastery import (
    apply_attempt_evidence,
    compute_confidence,
    AttemptKind,
)


def test_compute_confidence_grows_with_evidence():
    c0 = compute_confidence(Decimal("1"), Decimal("1"))
    c5 = compute_confidence(Decimal("4"), Decimal("2"))
    c50 = compute_confidence(Decimal("30"), Decimal("21"))
    assert c0 < c5 < c50
    assert 0 <= c0 < 1 and 0 <= c5 < 1 and 0 <= c50 < 1


@pytest.mark.asyncio
async def test_apply_attempt_correct_grows_alpha(db_session, test_instructor):
    from app.models import (
        Concept, ConceptMastery, ConceptMasteryHistory,
        ConceptTag, Course,
    )
    course = Course(
        instructor_id=test_instructor.id, name="C", language="english", enroll_code="CMA01",
    )
    db_session.add(course)
    await db_session.commit()
    c1 = Concept(course_id=course.id, name="A", status="approved", instructor_curated=True)
    c2 = Concept(course_id=course.id, name="B", status="approved", instructor_curated=True)
    db_session.add_all([c1, c2])
    await db_session.commit()

    target_id = uuid.uuid4()
    db_session.add_all([
        ConceptTag(
            concept_id=c1.id, target_kind="question", target_id=target_id,
            weight=Decimal("1.00"),
        ),
        ConceptTag(
            concept_id=c2.id, target_kind="question", target_id=target_id,
            weight=Decimal("0.50"),
        ),
    ])
    await db_session.commit()

    await apply_attempt_evidence(
        db_session,
        user_id=test_instructor.id,
        course_id=course.id,
        target_kind="question",
        target_id=target_id,
        attempt_kind=AttemptKind.QUIZ,
        outcome=1.0,
    )
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(ConceptMastery).where(ConceptMastery.user_id == test_instructor.id)
        )
    ).scalars().all()
    by_concept = {r.concept_id: r for r in rows}
    # c1 weight 1.0 → α = 1 + 1.0 = 2.0; β stays 1.0
    assert float(by_concept[c1.id].alpha) == pytest.approx(2.0)
    assert float(by_concept[c1.id].beta) == pytest.approx(1.0)
    # c2 weight 0.5 → α = 1 + 0.5; β stays 1.0
    assert float(by_concept[c2.id].alpha) == pytest.approx(1.5)

    history = (
        await db_session.execute(select(ConceptMasteryHistory))
    ).scalars().all()
    assert len(history) == 2
    assert all(h.event_type == "attempt" for h in history)


@pytest.mark.asyncio
async def test_apply_attempt_no_tags_is_noop(db_session, test_instructor):
    from app.models import ConceptMastery, Course
    course = Course(
        instructor_id=test_instructor.id, name="C", language="english", enroll_code="CMA02",
    )
    db_session.add(course)
    await db_session.commit()

    await apply_attempt_evidence(
        db_session,
        user_id=test_instructor.id,
        course_id=course.id,
        target_kind="question",
        target_id=uuid.uuid4(),
        attempt_kind=AttemptKind.QUIZ,
        outcome=1.0,
    )
    await db_session.commit()
    rows = (
        await db_session.execute(select(ConceptMastery))
    ).scalars().all()
    assert rows == []
