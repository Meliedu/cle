"""Dev-only demo seed for the Meli × CLE checkpoint-loop pilot.

Creates a realistic, walkable dataset for manual + Playwright testing of the
built P0–P2 surface (sign-in → role routing → teacher overview/enrollment →
student join). Seeds ONLY the ``public`` schema (users, a published CLE course,
sessions, score categories, materials, enrollments). The matching Better Auth
credential rows (``auth`` schema, bcrypt password, emailVerified=true) are
created by ``frontend/scripts/seed-auth.mjs`` using the SAME deterministic ids.

Idempotent: deletes any prior demo rows (by the fixed demo codes/emails) and
recreates them. Refuses to run when ENVIRONMENT=production so no demo data can
leak into a production database (compliance register: "remove ALL test data and
test accounts before production").

Run:  backend/.venv/Scripts/python.exe seed_demo.py
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, select

from app.config import settings
from app.database import async_session_factory
from app.models.course import Course, Enrollment
from app.models.curriculum import CourseMeeting, LearningObjective
from app.models.document import Document
from app.models.score import ScoreCategory
from app.models.user import User

# --- Fixed demo identity constants (shared with frontend/scripts/seed-auth.mjs) ---
DEMO_PASSWORD = "MeliDemo2026!"

TEACHER = {
    "better_auth_id": "demo-teacher",
    "email": "meli.teacher@ust.hk",
    "full_name": "Dr. Wei Chen",
    "role": "instructor",
}
STUDENT = {
    "better_auth_id": "demo-student",
    "email": "meli.student@connect.ust.hk",
    "full_name": "Aidan Lam",
    "role": "student",
}
STUDENT_PENDING = {
    "better_auth_id": "demo-student-2",
    "email": "meli.pending@connect.ust.hk",
    "full_name": "Priya Nair",
    "role": "student",
}
DEMO_USERS = [TEACHER, STUDENT, STUDENT_PENDING]
DEMO_EMAILS = [u["email"] for u in DEMO_USERS]

PUBLISHED_CODE = "LANG1511"
DRAFT_CODE = "LANG1513"
DEMO_COURSE_CODES = [PUBLISHED_CODE, DRAFT_CODE]

# Fall term anchor (Mon 2026-09-01 09:30 HKT ≈ 01:30 UTC).
TERM_START = datetime(2026, 9, 1, 1, 30, tzinfo=timezone.utc)

SESSION_TOPICS = [
    ("拼音与声调基础 · Pinyin & Tones", "Sound system, four tones, tone sandhi drills."),
    ("课堂用语与自我介绍 · Classroom Language", "Greetings, self-introduction, question words."),
    ("数字、时间与日期 · Numbers & Time", "Counting, telling time, scheduling vocabulary."),
    ("校园生活 · Campus Life", "Describing daily routine on campus; location words."),
    ("点餐与饮食 · Food & Ordering", "Restaurant dialogue, measure words for food."),
    ("购物与议价 · Shopping", "Prices, colours, sizes; comparison structures."),
    ("方向与交通 · Directions & Transit", "Asking directions, MTR/bus vocabulary."),
    ("兴趣爱好 · Hobbies", "Talking about free-time activities; frequency adverbs."),
    ("家庭与朋友 · Family & Friends", "Kinship terms, describing people."),
    ("天气与季节 · Weather & Seasons", "Weather patterns, seasonal activities."),
    ("学业与未来 · Studies & Plans", "Majors, plans, expressing intention (要/想/打算)."),
    ("复习与口语汇报 · Review & Oral", "Integrated review; short oral presentation."),
]

SCORE_CATEGORIES = [
    ("Participation & Attendance", Decimal("15"), 0),
    ("Session Checkpoints", Decimal("20"), 1),
    ("Practice & Quizzes", Decimal("25"), 2),
    ("Class Activities", Decimal("10"), 3),
    ("Final Oral & Written", Decimal("30"), 4),
]

MATERIALS = [
    ("LANG1511_Syllabus_2026Fall.pdf", "syllabus", "pdf", 8),
    ("Unit01_Pinyin_and_Tones.pdf", "lecture", "pdf", 24),
    ("Unit02_Classroom_Language.pptx", "lecture", "pptx", 18),
    ("Radicals_Reference_Sheet.pdf", "reference", "pdf", 4),
    ("Listening_Practice_Week1.mp3", "reading", "mp3", None),
]

FULL_CHECKLIST = {
    "basics": True,
    "syllabus": True,
    "materials": True,
    "schedule": True,
    "analyzer_review": True,
    "ilo_map": True,
    "checkpoints": True,
    "score_policy": True,
    "class_code": True,
}


async def _purge(session) -> None:
    """Delete prior demo courses (cascades enrollments/meetings/docs/scores)
    and demo users, so re-running produces a clean, deterministic dataset."""
    course_rows = (
        await session.execute(select(Course).where(Course.code.in_(DEMO_COURSE_CODES)))
    ).scalars().all()
    for course in course_rows:
        await session.delete(course)  # ORM cascade covers enrollments
    await session.flush()

    # Meetings/docs/score categories cascade via FK ON DELETE CASCADE, but the
    # ORM relationship cascade only covers enrollments — clear the rest by course.
    await session.execute(delete(User).where(User.email.in_(DEMO_EMAILS)))
    await session.commit()


async def seed() -> None:
    if settings.environment == "production":
        raise SystemExit("Refusing to seed demo data with ENVIRONMENT=production.")

    async with async_session_factory() as session:
        await _purge(session)

        # --- Users ---
        teacher = User(**TEACHER, notification_prefs={})
        student = User(**STUDENT, notification_prefs={})
        pending = User(**STUDENT_PENDING, notification_prefs={})
        session.add_all([teacher, student, pending])
        await session.flush()

        # --- Published course (walkable overview / enrollment / join) ---
        published = Course(
            name="LANG1511 · Chinese I for Non-Chinese Speakers",
            code=PUBLISHED_CODE,
            description=(
                "Introductory Mandarin for HKUST students with no prior Chinese. "
                "Builds foundational listening, speaking, reading and writing "
                "through weekly checkpoint-driven practice."
            ),
            language="chinese",
            semester="2026-fall",
            instructor_id=teacher.id,
            enroll_code="MELI1511",
            context_status="approved",
            context_approved_at=datetime.now(timezone.utc),
            setup_status="published",
            setup_checklist=FULL_CHECKLIST,
            join_mode="code_plus_approval",
            enroll_code_active=True,
        )
        # --- Draft course (walkable setup-in-progress) ---
        draft = Course(
            name="LANG1513 · Chinese III",
            code=DRAFT_CODE,
            description="Intermediate Mandarin — course setup in progress.",
            language="chinese",
            semester="2026-fall",
            instructor_id=teacher.id,
            enroll_code="MELI1513",
            context_status="draft",
            setup_status="draft",
            setup_checklist={"basics": True, "syllabus": True},
            join_mode="code",
            enroll_code_active=False,
        )
        session.add_all([published, draft])
        await session.flush()

        # --- Sessions (course_meetings) ---
        for i, (title, summary) in enumerate(SESSION_TOPICS):
            if i < 3:
                release = "completed"
            elif i == 3:
                release = "released"
            else:
                release = "locked"
            session.add(
                CourseMeeting(
                    course_id=published.id,
                    meeting_index=i + 1,
                    title=f"Session {i + 1} · {title}",
                    scheduled_at=TERM_START + timedelta(weeks=i),
                    duration_minutes=80,
                    location="Rm 2464, Lift 25-26" if i % 2 == 0 else "Rm 1410, Lift 25-26",
                    status="taught" if i < 3 else "planned",
                    release_state=release,
                    topic_summary=summary,
                )
            )

        # --- Learning objectives (ILO map) ---
        for j, stmt in enumerate(
            [
                "Produce the four Mandarin tones accurately in isolation and in words.",
                "Hold a short self-introduction conversation using classroom language.",
                "Recognise and write 150 high-frequency characters.",
                "Order food and shop using appropriate measure words and prices.",
                "Ask for and give directions around campus and the city.",
            ]
        ):
            session.add(
                LearningObjective(
                    course_id=published.id, statement=stmt, bloom_level="apply", order_index=j
                )
            )

        # --- Score categories ---
        for name, weight, sort in SCORE_CATEGORIES:
            session.add(
                ScoreCategory(course_id=published.id, name=name, weight=weight, sort=sort)
            )

        # --- Materials (documents) ---
        for filename, kind, ftype, pages in MATERIALS:
            session.add(
                Document(
                    course_id=published.id,
                    uploaded_by=teacher.id,
                    filename=filename,
                    file_type=ftype,
                    file_size=(pages or 3) * 120_000,
                    r2_key=f"demo/{published.id}/{filename}",
                    status="ready",
                    page_count=pages,
                    word_count=(pages or 0) * 320 or None,
                    kind=kind,
                )
            )

        # --- Enrollments ---
        session.add_all(
            [
                Enrollment(course_id=published.id, user_id=teacher.id, role="instructor", status="active"),
                Enrollment(course_id=published.id, user_id=student.id, role="student", status="active"),
                Enrollment(course_id=published.id, user_id=pending.id, role="student", status="pending"),
            ]
        )

        await session.commit()

        print("Demo seed complete:")
        print(f"  teacher  {teacher.email}  (course {published.code}, code MELI1511)")
        print(f"  student  {student.email}  (enrolled active)")
        print(f"  pending  {pending.email}  (join request pending approval)")
        print(f"  password for all: {DEMO_PASSWORD}")
        print("  next: run  frontend/scripts/seed-auth.mjs  to create login credentials")


if __name__ == "__main__":
    asyncio.run(seed())
