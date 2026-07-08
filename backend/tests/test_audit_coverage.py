"""P7 Task H4: audit-coverage check.

A single **coverage MAP** enumerating every AUDITED action in the P5–P7 surface.
Each entry drives the real endpoint through its happy path and asserts EXACTLY
ONE append-only audit row lands — in ``audit_events`` for the general audit log
(``report.approve`` / ``report.send`` / ``report.export`` / ``memory.decide`` /
``memory.import``) or in ``grade_exports`` for the P5 CSV export (Decision 7).

Why a map (not N ad-hoc tests): if a NEW mutating audited endpoint lands WITHOUT
an audit write, adding its row to ``AUDIT_COVERAGE`` here fails loudly until the
endpoint writes its row — the check is the living registry of "what must be
audited". Each ``driver`` sets up minimal rows, hits the endpoint via
``async_client`` (auth = ``logged_in_user``, an instructor course-owner), and
returns ``(model, filters)`` so the generic assertion below counts exactly one
matching row regardless of which table the action audits to.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import Course, User
from app.models.audit_event import AuditEvent
from app.models.evidence import CourseRecordItem, LearningNote
from app.models.report import Report
from app.models.score import GradeExport


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _make_course(
    db_session, instructor: User, *, code=None, enroll_code="AUDCOV01"
) -> Course:
    course = Course(
        name="Audit Coverage",
        language="english",
        code=code,
        instructor_id=instructor.id,
        enroll_code=enroll_code,
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _make_report(
    db_session, course: Course, *, status: str, evidence_refs=None
) -> Report:
    now = _utcnow()
    report = Report(
        course_id=course.id,
        audience="student",
        user_id=None,
        period="weekly",
        period_start=now - timedelta(days=7),
        period_end=now,
        body={"summary": "ok"},
        evidence_refs=evidence_refs if evidence_refs is not None else [],
        status=status,
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    return report


async def _make_reviewed_note(db_session, course: Course) -> LearningNote:
    note = LearningNote(
        course_id=course.id,
        observed_signal="signal",
        review_status="reviewed",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


async def _make_record_item(db_session, course: Course, **kwargs) -> CourseRecordItem:
    item = CourseRecordItem(
        course_id=course.id,
        outcome_summary={"status": "persistent"},
        **kwargs,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


# ---------------------------------------------------------------------------
# Drivers — each sets up minimal state, drives the REAL endpoint (happy path),
# and returns (audit-model, filters) scoping the ONE row it must have written.
# ---------------------------------------------------------------------------
async def _drive_report_approve(async_client, db_session, user):
    course = await _make_course(db_session, user, enroll_code="AUDAPP01")
    report = await _make_report(db_session, course, status="draft")
    r = await async_client.post(f"/api/reports/{report.id}/approve")
    assert r.status_code == 200, r.text
    return AuditEvent, {"event_type": "report.approve", "target_id": report.id}


async def _drive_report_send(async_client, db_session, user):
    course = await _make_course(db_session, user, enroll_code="AUDSND01")
    note = await _make_reviewed_note(db_session, course)
    report = await _make_report(
        db_session, course, status="reviewed", evidence_refs=[note.id]
    )
    r = await async_client.post(f"/api/reports/{report.id}/send")
    assert r.status_code == 200, r.text
    return AuditEvent, {"event_type": "report.send", "target_id": report.id}


async def _drive_report_export(async_client, db_session, user):
    course = await _make_course(db_session, user, enroll_code="AUDEXP01")
    note = await _make_reviewed_note(db_session, course)
    report = await _make_report(
        db_session, course, status="reviewed", evidence_refs=[note.id]
    )
    r = await async_client.post(f"/api/reports/{report.id}/export")
    assert r.status_code == 200, r.text
    return AuditEvent, {"event_type": "report.export", "target_id": report.id}


async def _drive_memory_decide(async_client, db_session, user):
    course = await _make_course(db_session, user, enroll_code="AUDDEC01")
    item = await _make_record_item(db_session, course)
    r = await async_client.post(
        f"/api/memory/{item.id}/decide", json={"decision": "keep"}
    )
    assert r.status_code == 200, r.text
    return AuditEvent, {"event_type": "memory.decide", "target_id": item.id}


async def _drive_memory_import(async_client, db_session, user):
    current = await _make_course(
        db_session, user, code="AUDLIN1", enroll_code="AUDIMPC1"
    )
    prior = await _make_course(
        db_session, user, code="AUDLIN1", enroll_code="AUDIMPP1"
    )
    item = await _make_record_item(
        db_session, prior, decision="carry_forward", carry_forward=True,
        instructor_comment="carry me forward",
    )
    r = await async_client.post(
        f"/api/courses/{current.id}/setup/import-memory",
        json={"item_ids": [str(item.id)]},
    )
    assert r.status_code == 200, r.text
    # Import audits with target_kind="course", target_id=the NEW course id.
    return AuditEvent, {"event_type": "memory.import", "target_id": current.id}


async def _drive_grade_export(async_client, db_session, user):
    course = await _make_course(db_session, user, enroll_code="AUDGRD01")
    r = await async_client.get(f"/api/courses/{course.id}/grade-export.csv")
    assert r.status_code == 200, r.text
    # The P5 CSV export audits to grade_exports (not audit_events), scoped by course.
    return GradeExport, {"course_id": course.id}


# The coverage MAP: (action label, event_type, audit table name, driver).
# Add a row here when a new audited endpoint lands — the test then FAILS until
# that endpoint writes exactly one audit row on its happy path.
AUDIT_COVERAGE = [
    ("report.approve", "report.approve", "audit_events", _drive_report_approve),
    ("report.send", "report.send", "audit_events", _drive_report_send),
    ("report.export", "report.export", "audit_events", _drive_report_export),
    ("memory.decide", "memory.decide", "audit_events", _drive_memory_decide),
    ("memory.import", "memory.import", "audit_events", _drive_memory_import),
    ("grade.export", None, "grade_exports", _drive_grade_export),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,event_type,table,driver",
    AUDIT_COVERAGE,
    ids=[row[0] for row in AUDIT_COVERAGE],
)
async def test_audited_action_writes_exactly_one_audit_row(
    async_client, db_session, logged_in_user, action, event_type, table, driver
):
    """Every audited action appends EXACTLY ONE append-only audit row.

    Drives the real endpoint happy path, then counts rows in the action's audit
    table scoped to the target it just acted on — asserting a single row proves
    the append-only write happened (and is not duplicated).
    """
    model, filters = await driver(async_client, db_session, logged_in_user)
    assert model.__tablename__ == table

    stmt = select(func.count()).select_from(model)
    for column, value in filters.items():
        stmt = stmt.where(getattr(model, column) == value)
    count = (await db_session.execute(stmt)).scalar_one()

    assert count == 1, (
        f"audited action '{action}' must write exactly one {table} row "
        f"(found {count}) with filters {filters}"
    )


def test_coverage_map_enumerates_all_known_audited_actions():
    """Guard: the coverage map lists every audited action we know ships today.

    A NEW audited endpoint added to the app without a row here is a coverage gap
    — this frozen expectation set forces the map to be updated deliberately.
    """
    covered = {row[0] for row in AUDIT_COVERAGE}
    expected = {
        "report.approve",
        "report.send",
        "report.export",
        "memory.decide",
        "memory.import",
        "grade.export",
    }
    assert covered == expected, (
        "AUDIT_COVERAGE drifted from the known audited-action set: "
        f"missing={expected - covered}, unexpected={covered - expected}"
    )
