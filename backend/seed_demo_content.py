"""Dev-only P3–P7 content seed for the demo LANG1511 course.

Layers realistic checkpoint-loop content on top of the base demo dataset
(``seed_demo.py``) so the P3–P7 surfaces render with real data instead of empty
states: checkpoints (+cards +student responses), a practice + graded quiz
(+questions), one class activity, the student checklist (work items + progress),
and weekly reports. Idempotent — clears this course's generated content first.

Run after seed_demo.py:  backend/.venv/Scripts/python.exe seed_demo_content.py
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, select

from app.config import settings
from app.database import async_session_factory
from app.models.activity import Activity
from app.models.checkpoint import Checkpoint, CheckpointCard, CheckpointResponse
from app.models.course import Course
from app.models.curriculum import CourseMeeting
from app.models.quiz import Question, Quiz
from app.models.report import Report
from app.models.score import ScoreCategory
from app.models.user import User
from app.models.work_item import WorkItem, WorkItemProgress

NOW = datetime.now(timezone.utc)


def due_on(days: int) -> datetime:
    """A due date `days` from now, pinned to 09:30 HKT (01:30 UTC) so checklist
    rows show a real class hour rather than the seed-run wall-clock time."""
    return (NOW + timedelta(days=days)).replace(
        hour=1, minute=30, second=0, microsecond=0
    )


async def seed() -> None:
    if settings.environment == "production":
        raise SystemExit("Refusing to seed demo content with ENVIRONMENT=production.")

    async with async_session_factory() as s:
        course = (
            await s.execute(select(Course).where(Course.code == "LANG1511"))
        ).scalar_one_or_none()
        if not course:
            raise SystemExit("Run seed_demo.py first — LANG1511 not found.")
        teacher = (
            await s.execute(select(User).where(User.email == "meli.teacher@ust.hk"))
        ).scalar_one()
        student = (
            await s.execute(select(User).where(User.email == "meli.student@connect.ust.hk"))
        ).scalar_one()
        meetings = (
            (
                await s.execute(
                    select(CourseMeeting)
                    .where(CourseMeeting.course_id == course.id)
                    .order_by(CourseMeeting.meeting_index)
                )
            )
            .scalars()
            .all()
        )
        score_cats = (
            (
                await s.execute(
                    select(ScoreCategory).where(ScoreCategory.course_id == course.id)
                )
            )
            .scalars()
            .all()
        )
        cid = course.id

        # --- Idempotency: clear this course's generated content ------------
        cp_ids = (
            await s.execute(select(Checkpoint.id).where(Checkpoint.course_id == cid))
        ).scalars().all()
        if cp_ids:
            await s.execute(
                delete(CheckpointResponse).where(
                    CheckpointResponse.checkpoint_id.in_(cp_ids)
                )
            )
        await s.execute(delete(Checkpoint).where(Checkpoint.course_id == cid))
        await s.execute(delete(Activity).where(Activity.course_id == cid))
        await s.execute(delete(WorkItem).where(WorkItem.course_id == cid))
        await s.execute(delete(Report).where(Report.course_id == cid))
        quiz_ids = (
            await s.execute(select(Quiz.id).where(Quiz.course_id == cid))
        ).scalars().all()
        await s.execute(delete(Quiz).where(Quiz.course_id == cid))
        await s.flush()

        work_items: list[tuple[str, object, str, bool, datetime | None, str]] = []

        # --- Checkpoints ----------------------------------------------------
        # A CLOSED checkpoint on session 1 (with the student's past responses)
        # + a PUBLISHED checkpoint on session 4 (open) + a DRAFT on session 5.
        def cards_for(cp_id, prompts: list[str]) -> list[CheckpointCard]:
            cards = [
                CheckpointCard(
                    checkpoint_id=cp_id, position=i, kind="review_point", prompt=p
                )
                for i, p in enumerate(prompts)
            ]
            cards.append(
                CheckpointCard(
                    checkpoint_id=cp_id,
                    position=len(prompts),
                    kind="final_comments",
                    prompt="Anything from today you'd like your teacher to revisit?",
                )
            )
            return cards

        # Closed checkpoint (session 1)
        cp_closed = Checkpoint(
            course_id=cid,
            meeting_id=meetings[0].id,
            kind="session",
            status="closed",
            title="Checkpoint · Pinyin & Tones",
            release_at=NOW - timedelta(days=7),
            close_at=NOW - timedelta(days=6, hours=22),
            close_rule="at_close_at",
            qr_enabled=True,
        )
        s.add(cp_closed)
        await s.flush()
        closed_cards = cards_for(
            cp_closed.id,
            [
                "I can produce the four tones accurately in isolation.",
                "I can hear the difference between 2nd and 3rd tone.",
                "I can read a syllable in pinyin and say it aloud.",
            ],
        )
        s.add_all(closed_cards)
        await s.flush()
        # Student responses to the closed checkpoint (confidence −2..+2 + final text)
        confidences = [2, -1, 1]
        for card, conf in zip(closed_cards[:3], confidences):
            s.add(
                CheckpointResponse(
                    checkpoint_id=cp_closed.id,
                    card_id=card.id,
                    user_id=student.id,
                    confidence=conf,
                    status="on_time",
                    submitted_at=NOW - timedelta(days=6, hours=23),
                )
            )
        s.add(
            CheckpointResponse(
                checkpoint_id=cp_closed.id,
                card_id=closed_cards[3].id,
                user_id=student.id,
                text_response="Third tone still trips me up in fast speech.",
                status="on_time",
                submitted_at=NOW - timedelta(days=6, hours=23),
            )
        )
        work_items.append(
            ("checkpoint", cp_closed.id, "Checkpoint · Pinyin & Tones", True, None, "completed")
        )

        # Published (open) checkpoint (session 4)
        cp_open = Checkpoint(
            course_id=cid,
            meeting_id=meetings[3].id,
            kind="session",
            status="published",
            title="Checkpoint · Campus Life",
            release_at=NOW - timedelta(hours=2),
            close_at=NOW + timedelta(days=3),
            close_rule="at_close_at",
            qr_enabled=True,
        )
        s.add(cp_open)
        await s.flush()
        s.add_all(
            cards_for(
                cp_open.id,
                [
                    "I can describe my daily routine on campus.",
                    "I can use location words (在, 旁边, 附近) correctly.",
                    "I can ask where a place is and understand the answer.",
                ],
            )
        )
        work_items.append(
            ("checkpoint", cp_open.id, "Checkpoint · Campus Life", True,
             due_on(3), "pending")
        )

        # Draft checkpoint (session 5) — for the studio editing view
        cp_draft = Checkpoint(
            course_id=cid,
            meeting_id=meetings[4].id,
            kind="session",
            status="draft",
            title="Checkpoint · Food & Ordering",
            qr_enabled=False,
        )
        s.add(cp_draft)
        await s.flush()
        s.add_all(
            cards_for(
                cp_draft.id,
                [
                    "I can order a meal using measure words.",
                    "I can ask the price and understand it.",
                ],
            )
        )

        # --- Quizzes --------------------------------------------------------
        def mc(idx: int, q: str, opts: list[str], correct: str, expl: str) -> dict:
            return dict(
                question_index=idx,
                type="multiple_choice",
                question_text=q,
                options=opts,
                correct_answer=correct,
                explanation=expl,
            )

        practice = Quiz(
            course_id=cid,
            created_by=teacher.id,
            title="Practice · Tones & Pinyin",
            description="Low-stakes retrieval practice on the first-unit sound system.",
            quiz_type="standard",
            purpose="after_class",
            assessment_purpose="practice",
            is_published=True,
        )
        s.add(practice)
        await s.flush()
        for spec in [
            mc(0, "How many tones does standard Mandarin have?", ["3", "4", "5", "6"], "4",
               "Mandarin has four main tones plus a neutral tone."),
            mc(1, "Which mark shows the first (high level) tone?", ["ā", "á", "ǎ", "à"], "ā",
               "The macron ˉ marks the high-level first tone."),
            mc(2, "The third tone is best described as…", ["rising", "falling", "falling-rising", "flat"],
               "falling-rising", "Tone 3 dips then rises."),
            mc(3, "‘mā’ (妈) most likely means…", ["mother", "horse", "scold", "hemp"], "mother",
               "First tone mā = 妈 (mother)."),
        ]:
            s.add(Question(quiz_id=practice.id, **spec))
        work_items.append(
            ("practice", practice.id, "Practice · Tones & Pinyin", False, None, "pending")
        )

        graded = Quiz(
            course_id=cid,
            created_by=teacher.id,
            title="Quiz · Unit 1 Vocabulary",
            description="Score-bearing check on Unit 1 core vocabulary.",
            quiz_type="standard",
            purpose="after_class",
            assessment_purpose="graded",
            is_published=True,
            score_bearing=True,
            score_category_id=(score_cats[2].id if len(score_cats) > 2 else None),
            points=Decimal("20"),
            grading_mode="auto",
            open_at=NOW - timedelta(days=1),
            due_at=NOW + timedelta(days=5),
            close_at=NOW + timedelta(days=6),
            late_rule="accept_with_flag",
        )
        s.add(graded)
        await s.flush()
        for spec in [
            mc(0, "你好 (nǐ hǎo) means…", ["goodbye", "hello", "thank you", "sorry"], "hello",
               "你好 is the standard greeting."),
            mc(1, "谢谢 (xièxie) means…", ["please", "hello", "thank you", "yes"], "thank you",
               "谢谢 = thank you."),
            mc(2, "Which is the number 'three'?", ["一", "二", "三", "四"], "三", "三 = 3."),
            mc(3, "老师 (lǎoshī) means…", ["student", "teacher", "friend", "classmate"], "teacher",
               "老师 = teacher."),
        ]:
            s.add(Question(quiz_id=graded.id, **spec))
        work_items.append(
            ("quiz", graded.id, "Quiz · Unit 1 Vocabulary", True,
             due_on(5), "in_progress")
        )

        # --- Activity -------------------------------------------------------
        activity = Activity(
            course_id=cid,
            meeting_id=meetings[1].id,
            format="vote",
            title="Vote · Which greeting fits a professor?",
            status="published",
            open_at=NOW - timedelta(hours=3),
            close_at=NOW + timedelta(days=2),
            anonymous=True,
            config={
                "prompt": "You meet Professor Chen in the corridor. Which greeting fits best?",
                "options": ["嗨! (Hi!)", "你好，陈老师", "喂", "早"],
            },
        )
        s.add(activity)
        await s.flush()
        work_items.append(
            ("activity", activity.id, "Vote · Which greeting fits a professor?", False,
             due_on(2), "pending")
        )

        # --- Work items + student progress ---------------------------------
        for source_kind, source_id, title, required, due_at, prog in work_items:
            wi = WorkItem(
                course_id=cid,
                source_kind=source_kind,
                source_id=source_id,
                title=title,
                required=required,
                score_bearing=(source_kind == "quiz"),
                due_at=due_at,
                visible_from=NOW - timedelta(days=8),
                created_by=teacher.id,
            )
            s.add(wi)
            await s.flush()
            s.add(
                WorkItemProgress(work_item_id=wi.id, user_id=student.id, status=prog)
            )

        # --- Reports --------------------------------------------------------
        teacher_body = {
            "summary": "Week 1 checkpoint completion was strong (1/1 responding). Tone 3 "
            "production is the main soft spot to revisit next session.",
            "completed_work": ["Checkpoint · Pinyin & Tones", "Practice · Tones & Pinyin"],
            "weak_points": ["Third-tone production in connected speech"],
            "next_actions": ["Insert a 5-minute tone-3 drill at the start of Session 2"],
            "claim_limits": "Based on one reviewed checkpoint; not a placement judgement.",
        }
        s.add(
            Report(
                course_id=cid,
                audience="teacher",
                user_id=None,
                period="weekly",
                period_start=NOW - timedelta(days=7),
                period_end=NOW,
                body=teacher_body,
                status="reviewed",
                reviewed_by=teacher.id,
                reviewed_at=NOW - timedelta(days=1),
            )
        )
        student_body = {
            "summary": "You completed your first checkpoint on time and reported solid "
            "confidence on tones overall.",
            "completed_work": ["Checkpoint · Pinyin & Tones"],
            "weak_points": ["Third tone in fast speech — worth a little more practice"],
            "next_actions": ["Try the Tones & Pinyin practice set once more before Session 2"],
            "claim_limits": "This describes your participation this week, not your ability.",
        }
        s.add(
            Report(
                course_id=cid,
                audience="student",
                user_id=student.id,
                period="weekly",
                period_start=NOW - timedelta(days=7),
                period_end=NOW,
                body=student_body,
                status="sent",
                reviewed_by=teacher.id,
                reviewed_at=NOW - timedelta(days=1),
                sent_at=NOW - timedelta(hours=20),
            )
        )

        await s.commit()
        print("P3–P7 content seeded for LANG1511:")
        print(f"  checkpoints: closed={cp_closed.id} open={cp_open.id} draft={cp_draft.id}")
        print(f"  quizzes: practice={practice.id} graded={graded.id}")
        print(f"  activity: {activity.id}")
        print(f"  work_items: {len(work_items)} (+ student progress)")
        print("  reports: 1 teacher weekly (reviewed) + 1 student weekly (sent)")


if __name__ == "__main__":
    asyncio.run(seed())
