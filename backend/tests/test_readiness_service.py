import pytest
from sqlalchemy import select

from app.models.course import Course
from app.models.readiness import ReadinessResponse
from app.services.readiness import ReadinessError, build_summary, submit_phase


async def _course(db_session, instructor):
    c = Course(
        name="LANG1511",
        language="zh",
        instructor_id=instructor.id,
        enroll_code="ABCD2345",
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest.mark.asyncio
async def test_submit_eligibility_survey_completes(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    row = await submit_phase(
        db_session,
        user=test_student,
        course=c,
        phase="eligibility_survey",
        answers={"prior_study": "1-3 years", "goals": ["Everyday conversation"]},
    )
    assert row.status == "completed"
    assert row.phase == "eligibility_survey"


@pytest.mark.asyncio
async def test_submit_unknown_phase_rejected(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    with pytest.raises(ReadinessError) as exc:
        await submit_phase(db_session, user=test_student, course=c, phase="bogus", answers={})
    assert exc.value.code == "UNKNOWN_PHASE"


@pytest.mark.asyncio
async def test_resubmit_upserts_not_duplicates(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    await submit_phase(
        db_session, user=test_student, course=c, phase="ready_check", answers={"conf_listening": 1}
    )
    await submit_phase(
        db_session, user=test_student, course=c, phase="ready_check", answers={"conf_listening": 2}
    )
    rows = (
        await db_session.execute(
            select(ReadinessResponse).where(
                ReadinessResponse.user_id == test_student.id,
                ReadinessResponse.course_id == c.id,
                ReadinessResponse.phase == "ready_check",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].answers["conf_listening"] == 2


@pytest.mark.asyncio
async def test_answer_shape_validation_rejects_unknown_question(
    db_session, test_instructor, test_student
):
    c = await _course(db_session, test_instructor)
    with pytest.raises(ReadinessError) as exc:
        await submit_phase(
            db_session,
            user=test_student,
            course=c,
            phase="eligibility_survey",
            answers={"prior_study": "Never", "made_up_key": "x"},
        )
    assert exc.value.code == "INVALID_ANSWERS"


@pytest.mark.asyncio
async def test_answer_shape_validation_accepts_known_subset(
    db_session, test_instructor, test_student
):
    c = await _course(db_session, test_instructor)
    # partial answers (known ids only) are fine — forward-compat, no hard require
    row = await submit_phase(
        db_session,
        user=test_student,
        course=c,
        phase="eligibility_survey",
        answers={"prior_study": "Never"},
    )
    assert row.status == "completed"


@pytest.mark.asyncio
async def test_recommendation_carries_claim_limit_copy(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    await submit_phase(
        db_session,
        user=test_student,
        course=c,
        phase="eligibility_survey",
        answers={"prior_study": "Never", "goals": []},
    )
    await submit_phase(
        db_session,
        user=test_student,
        course=c,
        phase="ready_check",
        answers={"conf_listening": -2, "conf_speaking": -1},
    )
    rec = await submit_phase(
        db_session, user=test_student, course=c, phase="recommendation", answers={}
    )
    assert "not a placement" in rec.result["claim_limit"].lower()
    assert rec.result["level_hint"]  # some coarse bucket string


@pytest.mark.asyncio
async def test_build_summary_lists_completed_phases(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    await submit_phase(
        db_session, user=test_student, course=c, phase="eligibility_survey", answers={}
    )
    summary = await build_summary(db_session, user=test_student, course=c)
    assert "eligibility_survey" in summary["completed_phases"]
    assert summary["recommendation"] is None  # not yet computed
