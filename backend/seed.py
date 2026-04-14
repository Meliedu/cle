import asyncio

from app.database import async_session_factory
from app.models.course import Course, Enrollment
from app.models.user import User


async def seed():
    async with async_session_factory() as session:
        instructor = User(
            clerk_id="dev_instructor_001",
            email="dev_instructor@ust.hk",
            full_name="Dr. Demo Instructor",
            role="instructor",
        )
        session.add(instructor)

        student = User(
            clerk_id="dev_student_001",
            email="dev_student@connect.ust.hk",
            full_name="Demo Student",
            role="student",
        )
        session.add(student)
        await session.flush()

        course = Course(
            name="Introduction to Chinese",
            code="LANG1010",
            description="Beginner Mandarin Chinese for international students",
            language="chinese",
            semester="2026-fall",
            instructor_id=instructor.id,
            enroll_code="DEMO2345",
        )
        session.add(course)
        await session.flush()

        session.add(Enrollment(course_id=course.id, user_id=instructor.id, role="instructor"))
        session.add(Enrollment(course_id=course.id, user_id=student.id, role="student"))

        await session.commit()
        print(f"Seeded: instructor={instructor.id}, student={student.id}, course={course.id}")


if __name__ == "__main__":
    asyncio.run(seed())
