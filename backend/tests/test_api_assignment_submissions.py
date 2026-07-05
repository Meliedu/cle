from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Assignment, AssignmentSubmission, Course, Enrollment, User


@pytest_asyncio.fixture
async def published_assignment(
    db_session: AsyncSession, logged_in_user: User, test_student: User,
) -> tuple[Course, Assignment]:
    course = Course(
        name="T", language="english",
        instructor_id=logged_in_user.id, enroll_code="SUBCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    a = Assignment(
        course_id=course.id, title="A", kind="essay",
        due_at=datetime.now(timezone.utc) + timedelta(days=3),
        is_published=True, created_by=logged_in_user.id,
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return course, a


@pytest.mark.asyncio
async def test_student_can_submit_own_submission(
    db_session: AsyncSession, test_student: User,
    published_assignment: tuple[Course, Assignment],
):
    course, assignment = published_assignment

    async def override_db():
        yield db_session

    async def override_user():
        return test_student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{course.id}/assignments/{assignment.id}/submission",
                json={"status": "submitted", "submission_payload": {"text": "hi"}},
            )
            assert r.status_code == 200
            assert r.json()["data"]["status"] == "submitted"
            assert r.json()["data"]["submitted_at"] is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_can_grade_submission(
    db_session: AsyncSession, logged_in_user: User, test_student: User,
    published_assignment: tuple[Course, Assignment],
):
    course, assignment = published_assignment
    sub = AssignmentSubmission(
        assignment_id=assignment.id, user_id=test_student.id, status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    async def override_db():
        yield db_session

    async def override_user():
        return logged_in_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{course.id}/assignments/{assignment.id}/submissions/{sub.id}/grade",
                json={"score": "85.00", "feedback": "Good", "status": "graded"},
            )
            assert r.status_code == 200
            assert r.json()["data"]["status"] == "graded"
            assert r.json()["data"]["score"] == "85.00"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Fix 1: IDOR tests — cross-course isolation for list_submissions / grade_submission
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def two_courses_with_assignments(
    db_session: AsyncSession,
) -> tuple[User, Course, Assignment, Course, Assignment]:
    """
    Instructor A owns course_a with assignment_a.
    Instructor B owns course_b with assignment_b.
    Returns (instructor_a, course_a, assignment_a, course_b, assignment_b).
    """
    instr_a = User(
        better_auth_id="idor_instr_a", email="idor_a@ust.hk",
        full_name="IDOR A", role="instructor",
    )
    instr_b = User(
        better_auth_id="idor_instr_b", email="idor_b@ust.hk",
        full_name="IDOR B", role="instructor",
    )
    db_session.add_all([instr_a, instr_b])
    await db_session.flush()

    course_a = Course(
        name="Course A", language="english",
        instructor_id=instr_a.id, enroll_code="IDORA001",
    )
    course_b = Course(
        name="Course B", language="english",
        instructor_id=instr_b.id, enroll_code="IDORB001",
    )
    db_session.add_all([course_a, course_b])
    await db_session.flush()

    db_session.add(Enrollment(course_id=course_a.id, user_id=instr_a.id, role="instructor"))
    db_session.add(Enrollment(course_id=course_b.id, user_id=instr_b.id, role="instructor"))

    asn_a = Assignment(
        course_id=course_a.id, title="Assignment A", kind="essay",
        due_at=datetime.now(timezone.utc) + timedelta(days=3),
        is_published=True, created_by=instr_a.id,
    )
    asn_b = Assignment(
        course_id=course_b.id, title="Assignment B", kind="essay",
        due_at=datetime.now(timezone.utc) + timedelta(days=3),
        is_published=True, created_by=instr_b.id,
    )
    db_session.add_all([asn_a, asn_b])
    await db_session.commit()
    await db_session.refresh(asn_a)
    await db_session.refresh(asn_b)
    return instr_a, course_a, asn_a, course_b, asn_b


@pytest.mark.asyncio
async def test_list_submissions_cross_course_idor_blocked(
    db_session: AsyncSession,
    two_courses_with_assignments: tuple,
):
    """Instructor A cannot list submissions for course B's assignment via course A's URL."""
    instr_a, course_a, asn_a, course_b, asn_b = two_courses_with_assignments

    async def override_db():
        yield db_session

    async def override_user():
        return instr_a

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            # Use course_a in URL but asn_b (belongs to course_b) as assignment_id
            r = await ac.get(
                f"/api/courses/{course_a.id}/assignments/{asn_b.id}/submissions",
            )
            assert r.status_code == 404, (
                f"Expected 404 (IDOR blocked), got {r.status_code}: {r.text}"
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_submit_after_due_is_recorded_late(
    db_session: AsyncSession, test_student: User, logged_in_user: User,
):
    """Posting status='submitted' after the deadline must be persisted as
    'late' regardless of what the client sent.

    Regression: client status was trusted, so a late submitter could be
    graded as on-time and adaptive signals (missed_deadline alerts,
    student_falling_behind) silently misclassified them.
    """
    course = Course(
        name="LateTest", language="english",
        instructor_id=logged_in_user.id, enroll_code="LATE-1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    a = Assignment(
        course_id=course.id, title="Past due", kind="essay",
        due_at=datetime.now(timezone.utc) - timedelta(hours=1),
        is_published=True, created_by=logged_in_user.id,
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)

    async def override_db():
        yield db_session

    async def override_user():
        return test_student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{course.id}/assignments/{a.id}/submission",
                json={"status": "submitted"},
            )
            assert r.status_code == 200
            assert r.json()["data"]["status"] == "late"
            assert r.json()["data"]["submitted_at"] is not None
    finally:
        app.dependency_overrides.clear()

    sub = (
        await db_session.execute(
            select(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id == a.id,
                AssignmentSubmission.user_id == test_student.id,
            )
        )
    ).scalar_one()
    assert sub.status == "late"


@pytest.mark.asyncio
async def test_submit_within_grace_window_is_on_time(
    db_session: AsyncSession, test_student: User, logged_in_user: User,
):
    """A submission landing within the 5-minute grace window is on-time.

    Absorbs client/server clock skew without misclassifying borderline
    submissions as late.
    """
    course = Course(
        name="Grace", language="english",
        instructor_id=logged_in_user.id, enroll_code="GRACE-1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    a = Assignment(
        course_id=course.id, title="Just past", kind="essay",
        due_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        is_published=True, created_by=logged_in_user.id,
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)

    async def override_db():
        yield db_session

    async def override_user():
        return test_student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{course.id}/assignments/{a.id}/submission",
                json={"status": "submitted"},
            )
            assert r.status_code == 200
            assert r.json()["data"]["status"] == "submitted"
    finally:
        app.dependency_overrides.clear()


async def test_grade_submission_cross_course_idor_blocked(
    db_session: AsyncSession,
    two_courses_with_assignments: tuple,
    test_student: User,
):
    """Instructor A cannot grade a submission on course B's assignment via course A's URL."""
    instr_a, course_a, asn_a, course_b, asn_b = two_courses_with_assignments

    # Create a submission for asn_b (course_b's assignment)
    sub = AssignmentSubmission(
        assignment_id=asn_b.id, user_id=test_student.id, status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    async def override_db():
        yield db_session

    async def override_user():
        return instr_a

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            # Use course_a in URL but asn_b (belongs to course_b) as assignment_id
            r = await ac.post(
                f"/api/courses/{course_a.id}/assignments/{asn_b.id}/submissions/{sub.id}/grade",
                json={"score": "100.00", "feedback": "Hacked", "status": "graded"},
            )
            assert r.status_code == 404, (
                f"Expected 404 (IDOR blocked), got {r.status_code}: {r.text}"
            )
    finally:
        app.dependency_overrides.clear()
