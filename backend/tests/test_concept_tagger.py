import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.services.concept_tagger import (
    tag_chunk_via_llm,
    inherit_tags_from_chunk,
)


@pytest.mark.asyncio
async def test_inherit_tags_from_chunk_scales_weight(db_session):
    from app.models import Concept, ConceptTag, Course, Chunk, Document, User
    user = User(better_auth_id="i", email="i@ust.hk", role="instructor", full_name="i")
    db_session.add(user)
    await db_session.commit()
    course = Course(instructor_id=user.id, name="C", language="english", enroll_code="X0001")
    db_session.add(course)
    await db_session.commit()
    doc = Document(
        course_id=course.id, filename="x.pdf", file_type="pdf",
        r2_key="k", status="completed", uploaded_by=user.id,
    )
    db_session.add(doc)
    await db_session.commit()
    chunk = Chunk(
        document_id=doc.id, course_id=course.id, content="...", chunk_index=0,
    )
    db_session.add(chunk)
    await db_session.commit()
    concept = Concept(
        course_id=course.id, name="Big-O", status="approved", instructor_curated=True,
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

    target_id = uuid.uuid4()
    await inherit_tags_from_chunk(
        db_session,
        source_chunk_id=chunk.id,
        target_kind="question",
        target_id=target_id,
    )
    await db_session.commit()

    from sqlalchemy import select
    rows = (
        await db_session.execute(
            select(ConceptTag).where(
                ConceptTag.target_kind == "question",
                ConceptTag.target_id == target_id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    # 1.00 * 0.7 = 0.70
    assert float(rows[0].weight) == pytest.approx(0.70, rel=1e-3)
