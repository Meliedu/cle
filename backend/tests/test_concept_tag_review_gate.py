"""Phase 6 — ConceptTag review gate (Relationship Candidate review, CLE §5.4).

Two surfaces:
1. ``app/services/concept_tagger.py`` — AI-created tags are inserted as
   ``review_status='suggested'`` with a ``suggestion_source`` provenance marker
   ('inheritance' for derived artifacts, 'llm' for chunk tagging).
2. ``app/api/concept_tags.py`` — PATCH endpoint where the *owning* instructor
   confirms/edits/archives a suggested tag, stamping ``reviewed_by`` /
   ``reviewed_at``. Non-owners get 404 (existence masked).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.api.deps import get_current_user
from app.main import app
from app.models import Concept, ConceptTag
from app.models.course import Course
from app.models.user import User
from app.services import concept_tagger


def _act_as(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda u=user: u


async def _make_course(db, instructor: User, code: str) -> Course:
    course = Course(
        instructor_id=instructor.id,
        name="C",
        language="english",
        enroll_code=code,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


async def _make_concept(db, course: Course, name: str = "Tone Sandhi") -> Concept:
    concept = Concept(
        course_id=course.id,
        name=name,
        status="approved",
        instructor_curated=True,
    )
    db.add(concept)
    await db.commit()
    await db.refresh(concept)
    return concept


_AUTH = {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_inherit_tags_marks_suggestion_inheritance(
    db_session, test_instructor
):
    """inherit_tags_from_chunk → new tag is 'suggested' via 'inheritance'."""
    course = await _make_course(db_session, test_instructor, "CT0001")
    concept = await _make_concept(db_session, course)

    chunk_id = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="chunk",
            target_id=chunk_id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    target_id = uuid.uuid4()
    inserted = await concept_tagger.inherit_tags_from_chunk(
        db_session,
        source_chunk_id=chunk_id,
        target_kind="question",
        target_id=target_id,
    )
    await db_session.commit()
    assert inserted == 1

    row = (
        await db_session.execute(
            select(ConceptTag).where(
                ConceptTag.target_kind == "question",
                ConceptTag.target_id == target_id,
            )
        )
    ).scalar_one()
    assert row.review_status == "suggested"
    assert row.suggestion_source == "inheritance"
    # weight × 0.7 inheritance factor.
    assert row.weight == Decimal("0.70")


@pytest.mark.asyncio
async def test_llm_tag_marks_suggestion_llm(
    db_session, test_instructor, monkeypatch
):
    """tag_chunk_via_llm → new tag is 'suggested' via 'llm' provenance."""
    course = await _make_course(db_session, test_instructor, "CT0002")
    concept = await _make_concept(db_session, course)

    async def _fake_llm_tag_call(text, candidates):
        return [{"concept_id": str(concept.id), "weight": 1.0}]

    monkeypatch.setattr(concept_tagger, "_llm_tag_call", _fake_llm_tag_call)

    chunk_id = uuid.uuid4()
    inserted = await concept_tagger.tag_chunk_via_llm(
        db_session,
        chunk_id=chunk_id,
        chunk_text="A passage about tone sandhi.",
        course_id=course.id,
    )
    await db_session.commit()
    assert inserted == 1

    row = (
        await db_session.execute(
            select(ConceptTag).where(
                ConceptTag.target_kind == "chunk",
                ConceptTag.target_id == chunk_id,
            )
        )
    ).scalar_one()
    assert row.review_status == "suggested"
    assert row.suggestion_source == "llm"


@pytest.mark.asyncio
async def test_owning_instructor_confirms_suggested_tag(
    client, db_session, test_instructor
):
    """PATCH review {confirmed} by owner → confirmed + reviewed_by/at stamped."""
    course = await _make_course(db_session, test_instructor, "CT0003")
    concept = await _make_concept(db_session, course)
    target_id = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="question",
            target_id=target_id,
            weight=Decimal("1.00"),
            review_status="suggested",
            suggestion_source="llm",
        )
    )
    await db_session.commit()

    _act_as(test_instructor)
    r = await client.patch(
        f"/api/concept-tags/{concept.id}/question/{target_id}/review",
        json={"review_status": "confirmed"},
        headers=_AUTH,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["review_status"] == "confirmed"

    row = (
        await db_session.execute(
            select(ConceptTag).where(
                ConceptTag.concept_id == concept.id,
                ConceptTag.target_kind == "question",
                ConceptTag.target_id == target_id,
            )
        )
    ).scalar_one()
    assert row.review_status == "confirmed"
    assert row.reviewed_by == test_instructor.id
    assert row.reviewed_at is not None


@pytest.mark.asyncio
async def test_non_owner_cannot_review_tag(
    client, db_session, test_instructor
):
    """PATCH review by a non-owning instructor → 404 (existence masked)."""
    course = await _make_course(db_session, test_instructor, "CT0004")
    concept = await _make_concept(db_session, course)
    target_id = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="question",
            target_id=target_id,
            weight=Decimal("1.00"),
            review_status="suggested",
            suggestion_source="llm",
        )
    )
    await db_session.commit()

    other_instructor = User(
        better_auth_id="dev_instructor_other",
        email="other-instructor@ust.hk",
        full_name="Other Instructor",
        role="instructor",
    )
    db_session.add(other_instructor)
    await db_session.commit()
    await db_session.refresh(other_instructor)

    _act_as(other_instructor)
    r = await client.patch(
        f"/api/concept-tags/{concept.id}/question/{target_id}/review",
        json={"review_status": "confirmed"},
        headers=_AUTH,
    )
    assert r.status_code == 404, r.text
