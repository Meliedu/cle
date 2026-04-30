import uuid
from datetime import datetime, timezone

import pytest

from app.models import (
    ActionOutcome,
    Concept,
    ConceptMastery,
    Course,
    Enrollment,
    NextAction,
    User,
)
from app.services.jobs import (
    run_materialize_next_actions,
    run_record_action_outcome,
)


@pytest.mark.asyncio
async def test_run_materialize_writes_rows(db_session, test_instructor: User, test_student: User):
    from decimal import Decimal

    course = Course(
        name="Worker mat",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="WM-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    c = Concept(course_id=course.id, name="t", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    result = await run_materialize_next_actions(
        db_session,
        {"user_id": str(test_student.id), "course_id": str(course.id)},
    )
    assert result["count"] >= 1


@pytest.mark.asyncio
async def test_run_record_action_outcome_persists_row(db_session, test_student: User):
    payload = {
        "user_id": str(test_student.id),
        "action_type": "do_quiz",
        "engine_variant": "off",
        "served_at": datetime.now(timezone.utc).isoformat(),
        "clicked": True,
        "completed": True,
        "outcome_metric": "quiz_score",
        "outcome_score": 0.83,
    }
    result = await run_record_action_outcome(db_session, payload)
    assert result["status"] == "recorded"
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(ActionOutcome).where(
            ActionOutcome.user_id == test_student.id
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].engine_variant == "off"


@pytest.mark.asyncio
async def test_horizon_scan_enqueues_for_enrolled_users(
    db_session, test_instructor: User, test_student: User
):
    from datetime import datetime, timedelta, timezone

    from app.models import Assignment, Enrollment, Task as TaskModel
    from app.services.worker import horizon_scan_recompute

    course = Course(
        name="Horizon",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="HZN-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    db_session.add(
        Assignment(
            course_id=course.id,
            title="Quiz tomorrow",
            kind="quiz",
            due_at=datetime.now(timezone.utc) + timedelta(hours=12),
            created_by=test_instructor.id,
        )
    )
    await db_session.commit()

    n = await horizon_scan_recompute(db_session)
    assert n >= 1
    queued = (await db_session.execute(
        __import__("sqlalchemy").select(TaskModel).where(
            TaskModel.task_type == "materialize_next_actions"
        )
    )).scalars().all()
    assert any(
        t.payload.get("user_id") == str(test_student.id) for t in queued
    )
