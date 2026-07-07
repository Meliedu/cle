"""B6 — skill pattern map (honest, config-driven, no fabricated scores).

Decision 5: the pilot ``skill_taxonomy`` (8 skills) exists in config, but NO
``skill`` link exists anywhere in the schema — ``concept_tags.target_kind`` has
``objective``/``checkpoint_card``/… but NOT ``skill``, and no evidence row
carries a skill dimension. So the skill-pattern map is a config-driven grid
where EVERY cell honestly renders the no-evidence state (``has_evidence=false``,
``strength=null``, ``sample_size=null``). It NEVER fabricates a score.

If a future concept→skill mapping lands, this test (and the endpoint docstring)
is the seam to extend: populate ``strength``/``sample_size`` and flip
``has_evidence`` only where real evidence exists.
"""
import uuid

import pytest

from app.api.deps import get_current_user
from app.main import app
from app.pilot import get_pilot_profile


async def _make_course(db_session, instructor):
    from app.models import Course
    course = Course(
        instructor_id=instructor.id,
        name="C", language="english", enroll_code=uuid.uuid4().hex[:8].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _enroll(db_session, course, student, status="active"):
    from app.models import Enrollment
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=student.id, role="student", status=status
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_skill_map_one_entry_per_taxonomy_skill_all_no_evidence(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    taxonomy = get_pilot_profile().skill_taxonomy

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/skill-map", headers=headers
        )
        assert r.status_code == 200
        data = r.json()["data"]
        # One entry per pilot taxonomy skill, in order.
        assert [e["skill"] for e in data["skills"]] == taxonomy
        assert len(data["skills"]) == len(taxonomy)
        # Decision 5: every cell is honestly the no-evidence state.
        assert data["has_evidence"] is False
        for entry in data["skills"]:
            assert entry["has_evidence"] is False
            # Forward-compatible shape, NULL today — never a fabricated score.
            assert entry["strength"] is None
            assert entry["sample_size"] is None
            # A human-readable label is always present.
            assert entry["label"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_skill_map_never_fabricates_a_score(
    client, db_session, test_instructor, test_student
):
    """Even for a student with real mastery rows, skill cells stay no-evidence.

    No concept→skill mapping exists, so mastery evidence CANNOT roll up into a
    skill score. The endpoint must not invent one.
    """
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/skill-map", headers=headers
        )
        assert r.status_code == 200
        for entry in r.json()["data"]["skills"]:
            assert entry["strength"] is None
            assert entry["sample_size"] is None
            assert entry["has_evidence"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_skill_map_403_when_not_active_enrollment(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    # Pending (not active) enrollment must be rejected by verify_enrollment.
    await _enroll(db_session, course, test_student, status="pending")

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/skill-map", headers=headers
        )
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_skill_map_403_when_never_enrolled(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    # No enrollment row at all.

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/skill-map", headers=headers
        )
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
