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
async def test_concurrent_attempts_dont_drop_evidence(
    db_session, test_instructor
):
    """Two attempts processed in concurrent sessions must both increment
    alpha — no lost-update.

    Regression: ``_get_or_create_mastery`` SELECT + Python read-modify-write
    let two workers read the same alpha=1.0 and each commit alpha=2.0,
    silently dropping one attempt's evidence.
    """
    import asyncio
    from app.models import Concept, ConceptMastery, ConceptTag, Course
    from tests.conftest import test_session_factory

    course = Course(
        instructor_id=test_instructor.id,
        name="Concurrent",
        language="english",
        enroll_code="CMA-CONC",
    )
    db_session.add(course)
    await db_session.commit()
    concept = Concept(
        course_id=course.id, name="x", status="approved",
        instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()
    target_id = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="question",
            target_id=target_id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    async def attempt_in_fresh_session() -> None:
        async with test_session_factory() as s:
            await apply_attempt_evidence(
                s,
                user_id=test_instructor.id,
                course_id=course.id,
                target_kind="question",
                target_id=target_id,
                attempt_kind=AttemptKind.QUIZ,
                outcome=1.0,
            )
            await s.commit()

    # Drive both attempts on the same event loop. Without atomic UPDATE the
    # async interleaving alone is enough to reproduce the lost-update bug.
    await asyncio.gather(
        attempt_in_fresh_session(),
        attempt_in_fresh_session(),
    )

    await db_session.rollback()  # refresh view
    row = (
        await db_session.execute(
            select(ConceptMastery).where(
                ConceptMastery.user_id == test_instructor.id,
                ConceptMastery.concept_id == concept.id,
            )
        )
    ).scalar_one()
    # Started at α=1.0 (PRIOR), each attempt adds weight·outcome = 1.0 → α=3.0
    assert float(row.alpha) == pytest.approx(3.0)
    assert row.attempt_count == 2


@pytest.mark.asyncio
async def test_apply_attempt_closes_concept_targeted_outcome(
    db_session, test_instructor
):
    """A practice_weakness next_action targets a concept; an attempt against
    a question tagged with that concept must close the open outcome row.

    Regression: outcome closure used to match by exact (target_kind, target_id),
    so concept-targeted recommendations never resolved completed=true and
    A/B telemetry undercounted successful adaptive nudges.
    """
    from datetime import datetime, timezone, timedelta
    from app.models import (
        ActionOutcome, Concept, ConceptTag, Course, NextAction,
    )

    course = Course(
        instructor_id=test_instructor.id,
        name="Concept close",
        language="english",
        enroll_code="CMA-CC",
    )
    db_session.add(course)
    await db_session.commit()
    concept = Concept(
        course_id=course.id, name="weakness", status="approved",
        instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()
    target_id = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="question",
            target_id=target_id,
            weight=Decimal("1.00"),
        )
    )
    now = datetime.now(timezone.utc)
    na = NextAction(
        user_id=test_instructor.id,
        course_id=course.id,
        action_type="practice_weakness",
        target_kind="concept",
        target_id=concept.id,
        priority_score=Decimal("1.500"),
        candidate_source="outer_fringe",
        reason={"concept_name": "weakness"},
        expires_at=now + timedelta(hours=1),
        served_at=now,
        engine_variant="on",
    )
    db_session.add(na)
    await db_session.commit()
    db_session.add(
        ActionOutcome(
            next_action_id=na.id,
            user_id=test_instructor.id,
            course_id=course.id,
            action_type="practice_weakness",
            target_kind="concept",
            target_id=concept.id,
            engine_variant="on",
            served_at=now,
        )
    )
    await db_session.commit()

    await apply_attempt_evidence(
        db_session,
        user_id=test_instructor.id,
        course_id=course.id,
        target_kind="question",  # NOT 'concept' — different artifact
        target_id=target_id,
        attempt_kind=AttemptKind.QUIZ,
        outcome=1.0,
    )
    await db_session.commit()

    outcome = (
        await db_session.execute(
            select(ActionOutcome).where(ActionOutcome.next_action_id == na.id)
        )
    ).scalar_one()
    assert outcome.completed is True
    assert float(outcome.outcome_score) == pytest.approx(1.0)
    assert outcome.outcome_metric == "quiz_score"


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


from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.mastery import hlr_decay_step, PRIOR


def test_hlr_decay_step_no_decay_without_last_attempt():
    a, b = hlr_decay_step(
        Decimal("5.000"), Decimal("2.000"), None, datetime.now(timezone.utc)
    )
    assert a == Decimal("5.000")
    assert b == Decimal("2.000")


def test_hlr_decay_step_zero_days_is_noop():
    now = datetime.now(timezone.utc)
    a, b = hlr_decay_step(Decimal("5.000"), Decimal("2.000"), now, now)
    assert a == Decimal("5.000")
    assert b == Decimal("2.000")


def test_hlr_decay_step_half_after_one_half_life():
    past = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = past + timedelta(days=14)  # default τ=14d → exactly one half-life
    a, b = hlr_decay_step(
        Decimal("5.000"), Decimal("3.000"), past, now, half_life_days=14
    )
    # Excess α=4 → 2; excess β=2 → 1; new α=3, β=2.
    assert float(a) == pytest.approx(3.0, abs=0.005)
    assert float(b) == pytest.approx(2.0, abs=0.005)


def test_hlr_decay_step_clamps_to_prior_floor():
    """Even after many half-lives, posterior never falls below the uniform prior."""
    past = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = past + timedelta(days=365)  # ~26 half-lives
    a, b = hlr_decay_step(
        Decimal("100.000"), Decimal("50.000"), past, now, half_life_days=14
    )
    assert a >= PRIOR
    assert b >= PRIOR
