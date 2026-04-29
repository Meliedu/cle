import pytest
import uuid
from decimal import Decimal

from app.models import Concept, ConceptPrerequisite, ConceptTag, Course, User


@pytest.mark.asyncio
async def test_concept_create_and_unique_lower_name(db_session, test_instructor):
    course = Course(
        instructor_id=test_instructor.id,
        name="Test",
        language="english",
        enroll_code="TEST1",
    )
    db_session.add(course)
    await db_session.commit()

    c1 = Concept(course_id=course.id, name="Big-O Notation")
    db_session.add(c1)
    await db_session.commit()

    # Duplicate (case-insensitive) on same course should fail
    c2 = Concept(course_id=course.id, name="big-o notation")
    db_session.add(c2)
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_concept_prerequisite_no_self(db_session, test_instructor):
    course = Course(
        instructor_id=test_instructor.id,
        name="T",
        language="english",
        enroll_code="TEST2",
    )
    db_session.add(course)
    await db_session.commit()

    c = Concept(course_id=course.id, name="X")
    db_session.add(c)
    await db_session.commit()

    bad = ConceptPrerequisite(prereq_concept_id=c.id, dependent_concept_id=c.id)
    db_session.add(bad)
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_concept_tag_role_only_for_meeting(db_session, test_instructor):
    course = Course(
        instructor_id=test_instructor.id,
        name="T",
        language="english",
        enroll_code="TEST3",
    )
    db_session.add(course)
    await db_session.commit()
    c = Concept(course_id=course.id, name="Y")
    db_session.add(c)
    await db_session.commit()

    # role on non-meeting target should violate CHECK constraint
    bad = ConceptTag(
        concept_id=c.id,
        target_kind="chunk",
        target_id=uuid.uuid4(),
        weight=Decimal("0.5"),
        role="introduced",
    )
    db_session.add(bad)
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()
