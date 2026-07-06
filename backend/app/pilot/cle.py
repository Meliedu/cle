"""HKUST CLE pilot profile — Chinese language courses (LANG1511-LANG1515)."""
from app.pilot.base import (
    ConfidenceScale,
    PilotProfile,
    ReadinessPhaseDef,
    ReadinessQuestion,
    ReportCadence,
    ScoreCategoryDefault,
)

CLE_PROFILE = PilotProfile(
    id="cle",
    institution="HKUST CLE",
    course_family="Chinese language courses (LANG1511-LANG1515)",
    terminology={
        "checkpoint": "Checkpoint",
        "session": "Session",
        "ilo": "ILO",
        "practice": "Practice",
        "activity": "Activity",
        "follow_up": "Follow-up",
        "course_memory": "Course Memory",
    },
    skill_taxonomy=[
        "reading",
        "speaking",
        "listening",
        "writing",
        "vocabulary",
        "grammar",
        "pronunciation",
        "task_comprehension",
    ],
    confidence_scale=ConfidenceScale(
        min=-2,
        max=2,
        labels={
            -2: "Not familiar at all",
            -1: "Heard of it, unsure",
            0: "Somewhat understand",
            1: "Understand well",
            2: "Could explain it to someone",
        },
    ),
    score_category_defaults=[
        ScoreCategoryDefault(name="Participation"),
        ScoreCategoryDefault(name="Quizzes"),
    ],
    readiness=[
        ReadinessPhaseDef(
            phase="eligibility_survey",
            title="Course Interest & Background",
            intro=(
                "A few short questions about your background with Chinese. "
                "This helps frame the course — it is not a test."
            ),
            questions=[
                ReadinessQuestion(
                    id="prior_study",
                    kind="single_choice",
                    prompt="How long have you studied Chinese before?",
                    options=["Never", "Under 1 year", "1-3 years", "3+ years"],
                ),
                ReadinessQuestion(
                    id="goals",
                    kind="multi_choice",
                    prompt="What do you most want from this course?",
                    options=[
                        "Everyday conversation",
                        "Reading & writing",
                        "Pronunciation",
                        "Academic/work use",
                    ],
                ),
            ],
        ),
        ReadinessPhaseDef(
            phase="ready_check",
            title="Ready Check",
            intro=(
                "Rate your confidence with these areas. Honest answers give "
                "you a more useful starting point."
            ),
            questions=[
                ReadinessQuestion(
                    id="conf_listening",
                    kind="scale",
                    prompt="Understanding spoken Mandarin",
                ),
                ReadinessQuestion(
                    id="conf_speaking",
                    kind="scale",
                    prompt="Speaking in everyday situations",
                ),
                ReadinessQuestion(
                    id="conf_reading",
                    kind="scale",
                    prompt="Reading simple passages",
                ),
                ReadinessQuestion(
                    id="conf_writing",
                    kind="scale",
                    prompt="Writing characters and short sentences",
                ),
            ],
        ),
    ],
    report_cadence=ReportCadence(weekly=True, end_term=True),
    role_rules={
        "ust.hk": "instructor",
        "connect.ust.hk": "student",
    },
    locales=["en", "zh-Hant"],
    claim_limits={
        "recommendation": (
            "This is guidance based on your survey answers, not a placement "
            "decision. Your instructor and the CLE make final course decisions."
        ),
        "learning_profile": (
            "This profile describes patterns in the course work you completed. "
            "It is not a judgment of your ability or identity."
        ),
        "report": (
            "This report summarizes reviewed course evidence. It describes "
            "observed participation and learning patterns only."
        ),
    },
)
