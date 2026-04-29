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
