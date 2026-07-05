import uuid
from decimal import Decimal

import pytest

from app.api.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_list_tags_for_target_returns_tagged_concept(
    client, db_session, test_instructor
):
    from app.models import Chunk, Concept, ConceptTag, Course, Document

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="TG0001",
    )
    db_session.add(course)
    await db_session.commit()

    doc = Document(
        course_id=course.id,
        filename="x.pdf",
        file_type="pdf",
        r2_key="k",
        status="completed",
        uploaded_by=test_instructor.id,
    )
    db_session.add(doc)
    await db_session.commit()

    chunk = Chunk(
        document_id=doc.id,
        course_id=course.id,
        content="...",
        chunk_index=0,
    )
    db_session.add(chunk)
    await db_session.commit()

    concept = Concept(
        course_id=course.id,
        name="Hash Table",
        status="approved",
        instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()

    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="chunk",
            target_id=chunk.id,
            weight=Decimal("0.85"),
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/concept-tags/chunk/{chunk.id}",
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        names = [c["name"] for c in body["data"]]
        assert "Hash Table" in names
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_tags_for_target_empty_when_no_tags(
    client, db_session, test_instructor
):
    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        target_id = uuid.uuid4()
        r = await client.get(
            f"/api/concept-tags/chunk/{target_id}",
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["data"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_tags_returns_empty_when_no_tags(client, db_session, test_instructor):
    """Untagged target returns empty list, NOT 404 (avoids leaking which
    artifacts are tagged)."""
    import uuid
    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(
            f"/api/concept-tags/chunk/{uuid.uuid4()}",
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 200
        assert r.json()["data"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_tags_returns_404_for_unenrolled_user(
    client, db_session, test_instructor, test_student
):
    """A student NOT enrolled in the course gets 404 even if tags exist."""
    from decimal import Decimal
    from app.models import Chunk, Concept, ConceptTag, Course, Document
    other_instructor_email = "other@ust.hk"
    from app.models import User
    other = User(
        better_auth_id="dev_other_h2",
        email=other_instructor_email,
        full_name="Other",
        role="instructor",
    )
    db_session.add(other)
    await db_session.commit()
    course = Course(
        instructor_id=other.id, name="Other Course",
        language="english", enroll_code="H2OTH",
    )
    db_session.add(course)
    await db_session.commit()
    doc = Document(
        course_id=course.id, filename="x.pdf", file_type="pdf",
        r2_key="k", status="completed", uploaded_by=other.id,
    )
    db_session.add(doc)
    await db_session.commit()
    chunk = Chunk(
        document_id=doc.id, course_id=course.id, content="...", chunk_index=0,
    )
    db_session.add(chunk)
    await db_session.commit()
    concept = Concept(
        course_id=course.id, name="Hidden", status="approved", instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()
    db_session.add(
        ConceptTag(
            concept_id=concept.id, target_kind="chunk", target_id=chunk.id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    # test_student is NOT enrolled in `course`.
    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(
            f"/api/concept-tags/chunk/{chunk.id}",
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_tags_returns_data_for_owner(client, db_session, test_instructor):
    """Owner of the course sees tagged concepts."""
    from decimal import Decimal
    from app.models import Chunk, Concept, ConceptTag, Course, Document
    course = Course(
        instructor_id=test_instructor.id, name="Mine",
        language="english", enroll_code="H2OWN",
    )
    db_session.add(course)
    await db_session.commit()
    doc = Document(
        course_id=course.id, filename="x.pdf", file_type="pdf",
        r2_key="k", status="completed", uploaded_by=test_instructor.id,
    )
    db_session.add(doc)
    await db_session.commit()
    chunk = Chunk(
        document_id=doc.id, course_id=course.id, content="...", chunk_index=0,
    )
    db_session.add(chunk)
    await db_session.commit()
    concept = Concept(
        course_id=course.id, name="Visible", status="approved", instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()
    db_session.add(
        ConceptTag(
            concept_id=concept.id, target_kind="chunk", target_id=chunk.id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(
            f"/api/concept-tags/chunk/{chunk.id}",
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 200
        names = [c["name"] for c in r.json()["data"]]
        assert "Visible" in names
    finally:
        app.dependency_overrides.clear()
