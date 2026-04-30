import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import ActionOutcome, Course, User
from app.services.action_coeffs import retune_action_coefficients


@pytest.mark.asyncio
async def test_retune_returns_per_action_summary(db_session, test_instructor: User):
    course = Course(
        name="Retune",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="RT-1",
    )
    db_session.add(course)
    await db_session.commit()

    served_at = datetime.now(timezone.utc) - timedelta(days=3)
    db_session.add_all([
        ActionOutcome(
            user_id=test_instructor.id, course_id=course.id,
            action_type="practice_weakness", engine_variant="on",
            served_at=served_at, completed=True,
            outcome_metric="quiz_score", outcome_score=Decimal("0.800"),
        ),
        ActionOutcome(
            user_id=test_instructor.id, course_id=course.id,
            action_type="practice_weakness", engine_variant="off",
            served_at=served_at, completed=True,
            outcome_metric="quiz_score", outcome_score=Decimal("0.500"),
        ),
    ])
    await db_session.commit()

    result = await retune_action_coefficients(db_session, window_days=30)
    assert "summary" in result
    summary = result["summary"]
    assert "practice_weakness" in summary
    pw = summary["practice_weakness"]
    assert pw["mean_outcome_on"] == pytest.approx(0.8, abs=1e-2)
    assert pw["mean_outcome_off"] == pytest.approx(0.5, abs=1e-2)
    assert pw["applied"] is False
