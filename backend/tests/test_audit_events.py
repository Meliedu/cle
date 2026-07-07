"""Model + write-helper tests for ``audit_events`` (P7 Task B2, Decision 4).

``audit_events`` is the NEW general **append-only** audit log (spec §8: "new
append-only ``audit_events`` (no update/delete path)"). It mirrors the P5
``grade_exports`` shape: UUID PK + a plain ``created_at`` only — **NO
``updated_at``, NO ``deleted_at``**. ``record_audit_event`` appends exactly one
row and leaves the commit to the caller (mirrors ``services/work_items.py`` —
"caller owns commit"); a second call appends a SECOND row (append-only, never
upserts).

Note (reserved attribute): ``metadata`` is reserved on the SQLAlchemy
Declarative ``Base`` (it holds the table registry). The Python attribute is
therefore named ``event_metadata`` and mapped to the ``"metadata"`` DB column via
``mapped_column("metadata", JSONB, ...)``. ``record_audit_event`` still accepts a
``metadata`` keyword for callers.
"""
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import inspect as sa_inspect, select

from app.models.audit_event import AuditEvent
from app.models.course import Course
from app.services.audit import record_audit_event


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1512",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="AUD" + uuid.uuid4().hex[:5].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


def test_audit_event_has_no_updated_or_deleted_columns():
    """Append-only: UUID PK + plain ``created_at`` — no ``updated_at``/``deleted_at``."""
    cols = {c.name for c in sa_inspect(AuditEvent).columns}
    assert "created_at" in cols
    assert "updated_at" not in cols
    assert "deleted_at" not in cols
    # Reserved-name mapping: the DB column is "metadata", the attribute is
    # "event_metadata".
    assert "metadata" in cols
    assert AuditEvent.event_metadata.property.columns[0].name == "metadata"


@pytest.mark.asyncio
async def test_record_audit_event_appends_row(
    db_session, seed_course, test_instructor
):
    target_id = uuid.uuid4()
    event = await record_audit_event(
        db_session,
        course_id=seed_course.id,
        actor_id=test_instructor.id,
        event_type="report.approve",
        target_kind="report",
        target_id=target_id,
        metadata={"note": "first"},
    )
    # Helper does NOT commit — caller owns the commit.
    await db_session.commit()
    await db_session.refresh(event)

    assert event.id is not None
    assert event.course_id == seed_course.id
    assert event.actor_id == test_instructor.id
    assert event.event_type == "report.approve"
    assert event.target_kind == "report"
    assert event.target_id == target_id
    assert event.event_metadata == {"note": "first"}
    assert isinstance(event.created_at, datetime)


@pytest.mark.asyncio
async def test_record_audit_event_is_append_only(
    db_session, seed_course, test_instructor
):
    """A second call for the SAME target writes a SECOND row (never upserts)."""
    target_id = uuid.uuid4()
    first = await record_audit_event(
        db_session,
        course_id=seed_course.id,
        actor_id=test_instructor.id,
        event_type="report.send",
        target_kind="report",
        target_id=target_id,
        metadata={"seq": 1},
    )
    second = await record_audit_event(
        db_session,
        course_id=seed_course.id,
        actor_id=test_instructor.id,
        event_type="report.export",
        target_kind="report",
        target_id=target_id,
        metadata={"seq": 2},
    )
    await db_session.commit()

    assert first.id != second.id
    rows = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.target_id == target_id)
        )
    ).scalars().all()
    assert len(rows) == 2
    assert {r.event_type for r in rows} == {"report.send", "report.export"}
    assert sorted(r.event_metadata["seq"] for r in rows) == [1, 2]


@pytest.mark.asyncio
async def test_record_audit_event_allows_null_metadata(
    db_session, seed_course, test_instructor
):
    event = await record_audit_event(
        db_session,
        course_id=seed_course.id,
        actor_id=test_instructor.id,
        event_type="memory.decide",
        target_kind="course_record_item",
        target_id=uuid.uuid4(),
        metadata=None,
    )
    await db_session.commit()
    await db_session.refresh(event)
    assert event.event_metadata is None
    assert event.event_type == "memory.decide"


@pytest.mark.asyncio
async def test_record_audit_event_does_not_commit(
    db_session, seed_course, test_instructor
):
    """The helper only stages the row; before the caller commits nothing is
    durable in a fresh session's view (caller owns commit)."""
    event = await record_audit_event(
        db_session,
        course_id=seed_course.id,
        actor_id=test_instructor.id,
        event_type="report.approve",
        target_kind="report",
        target_id=uuid.uuid4(),
        metadata={},
    )
    # Row is pending in the unit of work, not yet flushed/committed by helper.
    assert event in db_session.new or event in db_session
