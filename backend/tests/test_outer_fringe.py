import uuid
from decimal import Decimal

import pytest

from app.models import (
    Concept,
    ConceptMastery,
    ConceptPrerequisite,
    Course,
    User,
)
from app.services.outer_fringe import outer_fringe_concepts


async def _seed_course_with_concepts(
    db_session, instructor: User, student: User
):
    course = Course(
        name="OF Course",
        language="en",
        instructor_id=instructor.id,
        enroll_code="OF-1",
    )
    db_session.add(course)
    await db_session.flush()

    a = Concept(course_id=course.id, name="A", status="approved")
    b = Concept(course_id=course.id, name="B", status="approved")
    c = Concept(course_id=course.id, name="C", status="approved")
    db_session.add_all([a, b, c])
    await db_session.flush()

    # B depends on A; C depends on B.
    db_session.add_all([
        ConceptPrerequisite(prereq_concept_id=a.id, dependent_concept_id=b.id, strength=Decimal("1.00")),
        ConceptPrerequisite(prereq_concept_id=b.id, dependent_concept_id=c.id, strength=Decimal("1.00")),
    ])
    await db_session.commit()
    return course, a, b, c


@pytest.mark.asyncio
async def test_no_mastery_yields_only_root(db_session, test_instructor: User, test_student: User):
    course, a, b, c = await _seed_course_with_concepts(db_session, test_instructor, test_student)
    rows = await outer_fringe_concepts(
        db_session, user_id=test_student.id, course_id=course.id
    )
    ids = {r.concept_id for r in rows}
    assert a.id in ids
    assert b.id not in ids and c.id not in ids


@pytest.mark.asyncio
async def test_mastered_root_unblocks_b(db_session, test_instructor: User, test_student: User):
    course, a, b, c = await _seed_course_with_concepts(db_session, test_instructor, test_student)
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=a.id, course_id=course.id,
            alpha=Decimal("8.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.700"),
        )
    )
    await db_session.commit()
    rows = await outer_fringe_concepts(
        db_session, user_id=test_student.id, course_id=course.id
    )
    ids = {r.concept_id for r in rows}
    assert b.id in ids and a.id not in ids and c.id not in ids


@pytest.mark.asyncio
async def test_low_confidence_prereq_blocks(db_session, test_instructor: User, test_student: User):
    course, a, b, c = await _seed_course_with_concepts(db_session, test_instructor, test_student)
    # Mastery is high but confidence is below 0.5 → A is not "really" mastered.
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=a.id, course_id=course.id,
            alpha=Decimal("3.000"), beta=Decimal("1.000"),
            confidence=Decimal("0.300"),
        )
    )
    await db_session.commit()
    rows = await outer_fringe_concepts(
        db_session, user_id=test_student.id, course_id=course.id
    )
    ids = {r.concept_id for r in rows}
    # A is still in the fringe (not yet mastered with confidence) so still
    # surfaces; B is blocked because A doesn't meet the prereq predicate.
    assert a.id in ids and b.id not in ids


@pytest.mark.asyncio
async def test_canonical_merged_concepts_excluded(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="OF canonical",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="OF-2",
    )
    db_session.add(course)
    await db_session.flush()
    canonical = Concept(course_id=course.id, name="canon", status="approved")
    db_session.add(canonical)
    await db_session.flush()
    merged = Concept(
        course_id=course.id, name="dup", status="merged",
        canonical_id=canonical.id,
    )
    db_session.add(merged)
    await db_session.commit()

    rows = await outer_fringe_concepts(
        db_session, user_id=test_student.id, course_id=course.id
    )
    ids = {r.concept_id for r in rows}
    assert canonical.id in ids and merged.id not in ids
