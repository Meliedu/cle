"""End-to-end placement tests: import, publish gate, delivery, review, release.

These run against the real item bank, so they cover the two things unit tests
cannot: that a learner's payload never contains a key, and that no path reaches
a released recommendation without a CLE decision.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.deps import get_current_user
from app.main import app
from app.models.placement import (
    PlacementAttempt,
    PlacementAuditEvent,
    PlacementForm,
    PlacementItem,
    PlacementItemKey,
    PlacementTestVersion,
)
from app.models.user import User
from app.services import placement as svc
from app.services import placement_bank

BANK_PATH = (
    Path(__file__).resolve().parents[1]
    / "app" / "data" / "placement" / "meli-placement-v1.3.json"
)
RULE_VERSION = "v1.3-candidate"

pytestmark = pytest.mark.asyncio


def _bank() -> dict:
    if not BANK_PATH.exists():  # pragma: no cover
        pytest.skip("item bank not generated")
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _disputed_bank() -> dict:
    """The real bank with one item's key marked disputed.

    v1.2 shipped two genuinely disputed items, so the gate could be tested
    against the real file. v1.3 revised them and preflights clean -- which is
    the outcome we want and also removes the natural fixture. Injecting the
    dispute keeps the gate under test on its own terms instead of leaving it
    exercised only by whichever defects a package happens to contain.
    """
    bank = _bank()
    item = bank["forms"][1]["items"][16]
    item["teacher_flags"] = [
        {
            "code": "key_disputed",
            "detail": "two options are defensible",
            "source": "test",
        }
    ]
    return bank


@pytest_asyncio.fixture
async def student(db_session) -> User:
    user = User(
        better_auth_id="placement_student_1",
        email="placement.student@connect.ust.hk",
        full_name="Placement Student",
        role="student",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def instructor(db_session) -> User:
    user = User(
        better_auth_id="placement_instructor_1",
        email="placement.instructor@ust.hk",
        full_name="Placement Instructor",
        role="instructor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(autouse=True)
def _bearer(client):
    """Give every request in this module a token-shaped Authorization header.

    The auth middleware does a cheap Bearer check before `get_current_user`
    (which each test overrides) is ever reached, so without this every call
    would 401 regardless of who the test says the caller is. The value is
    irrelevant -- the override decides identity.
    """
    client.headers["Authorization"] = "Bearer test-token"
    return client


def _as(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


@pytest_asyncio.fixture
async def published(db_session) -> PlacementTestVersion:
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version=RULE_VERSION
    )
    version.status = "published"
    version.published_at = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(version)
    return version


# ---------------------------------------------------------------------------
# Import + publication gate
# ---------------------------------------------------------------------------


async def test_import_creates_five_forms_and_one_hundred_fifty_items(db_session):
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()

    forms = (
        await db_session.execute(
            select(PlacementForm).where(PlacementForm.test_version_id == version.id)
        )
    ).scalars().all()
    assert sorted(f.form_code for f in forms) == ["A", "B", "C", "D", "E"]
    assert await placement_bank.count_items(db_session, version.id) == 150


async def test_import_lands_as_candidate_never_published(db_session):
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()
    assert version.status == "candidate"


async def test_importing_the_same_version_twice_is_refused(db_session):
    await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()
    with pytest.raises(placement_bank.PlacementBankError) as excinfo:
        await placement_bank.import_bank(
            db_session, _bank(), scoring_rule_version=RULE_VERSION
        )
    assert excinfo.value.code == "VERSION_EXISTS"


async def test_the_real_v1_3_package_preflights_clean(db_session):
    """The shipped v1.3 package must carry no blocking finding.

    This is the assertion v1.3 exists to satisfy: the three items the teacher
    disputed in v1.2 were revised, so nothing is left that would make a score
    indefensible. It is deliberately an assertion about the *real* file --
    if a future package reintroduces a disputed key, an unscoreable option set
    or a mis-numbered cloze blank, this fails before anyone tries to publish.
    """
    bank = _bank()
    result = placement_bank.preflight_bank(bank)
    assert result.blocking == (), [f.as_dict() for f in result.blocking]

    version = await placement_bank.import_bank(
        db_session, bank, scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()
    stored = await placement_bank.preflight_version(db_session, version)
    assert stored.can_publish is True, [f.as_dict() for f in stored.blocking]


async def test_the_teacher_re_review_ledger_survives_import(db_session):
    """Advisory findings still reach the reviewer.

    Clean does not mean silent: the 22 items carrying incorporated v1.2
    feedback are exactly what CLE has to confirm, so they must arrive as
    advisory findings rather than being dropped for not blocking.
    """
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()

    result = await placement_bank.preflight_version(db_session, version)
    advisory = [f for f in result.findings if f.code == "teacher_feedback_incorporated"]
    assert len(advisory) == 22
    assert all(f.severity == "advisory" for f in advisory)
    assert all(f.external_item_id for f in advisory)


async def test_the_item_review_ledger_reaches_storage(db_session):
    """The v1.3 ledger row must actually be persisted, not silently dropped.

    ``import_bank`` names every column it writes, so a field added to the bank
    without a matching column is discarded in silence and the review screen
    quietly loses the thing it was added for. This asserts the round trip.
    """
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(PlacementItemKey.teacher_review).where(
                PlacementItemKey.test_version_id == version.id
            )
        )
    ).scalars().all()

    assert len(rows) == 150
    assert all(row is not None for row in rows)
    assert all(row.get("review_question") for row in rows)
    assert {row.get("teacher_priority") for row in rows} <= {"High", "Medium", "Low"}


async def test_preflight_blocks_publication_on_a_teacher_disputed_key(db_session):
    """An item whose key the content owner disputes cannot be published.

    Scoring it would produce a number nobody can defend, so the gate holds
    regardless of how clean the rest of the package is.
    """
    version = await placement_bank.import_bank(
        db_session, _disputed_bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()

    result = await placement_bank.preflight_version(db_session, version)
    assert result.can_publish is False
    assert "key_disputed" in {f.code for f in result.blocking}


async def test_publish_endpoint_refuses_a_version_with_blocking_findings(
    client, db_session, instructor
):
    version = await placement_bank.import_bank(
        db_session, _disputed_bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()
    _as(instructor)

    response = await client.post(f"/api/placement/versions/{version.id}/publish")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PREFLIGHT_FAILED"

    await db_session.refresh(version)
    assert version.status == "candidate"


async def test_publish_succeeds_once_the_content_is_settled(
    client, db_session, instructor
):
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()
    _as(instructor)

    response = await client.post(f"/api/placement/versions/{version.id}/publish")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "published"


async def test_publishing_is_audited(client, db_session, instructor):
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()
    _as(instructor)
    await client.post(f"/api/placement/versions/{version.id}/publish")

    events = (
        await db_session.execute(
            select(PlacementAuditEvent).where(
                PlacementAuditEvent.event_type == "placement.version.published"
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].actor_id == instructor.id


async def test_a_student_cannot_publish_a_version(client, db_session, student):
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version=RULE_VERSION
    )
    await db_session.commit()
    _as(student)
    response = await client.post(f"/api/placement/versions/{version.id}/publish")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Student delivery
# ---------------------------------------------------------------------------


async def test_intro_states_the_claim_boundary_and_attempt_policy(
    client, published, student
):
    _as(student)
    response = await client.get("/api/placement")
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["total_items"] == 30
    assert data["section_counts"] == {"listening": 12, "language_use": 6, "reading": 12}
    assert data["max_attempts"] == 3
    assert data["attempts_remaining"] == 3
    assert "not an official HSK" in data["purpose"]
    assert "not statistically equated" in data["comparability_note"]


async def test_no_published_version_is_a_state_not_an_error(client, db_session, student):
    """"The test is not open" answers the question; it is not a failure.

    A 5xx here would log a console error on a page that is working correctly and
    would tell monitoring the service is down when it is merely between windows.
    """
    _as(student)
    response = await client.get("/api/placement")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is False
    assert data["unavailable_reason"] == "not_published"


async def test_a_closed_window_is_reported_as_unavailable(
    client, db_session, published, student
):
    published.window_opens_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db_session.commit()

    _as(student)
    data = (await client.get("/api/placement")).json()["data"]
    assert data["available"] is False
    assert data["unavailable_reason"] == "window_closed"
    # The learner is told when it opens rather than just that it is shut.
    assert data["window_opens_at"] is not None


async def test_an_open_test_reports_itself_available(client, published, student):
    _as(student)
    data = (await client.get("/api/placement")).json()["data"]
    assert data["available"] is True
    assert data["unavailable_reason"] is None


async def test_starting_an_attempt_allocates_a_form(client, published, student):
    _as(student)
    response = await client.post("/api/placement/attempts", json={})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["state"] == "created"
    assert data["form_code"] in {"A", "B", "C", "D", "E"}
    assert data["attempt_number"] == 1


async def test_pressing_start_twice_resumes_rather_than_burning_an_attempt(
    client, published, student
):
    _as(student)
    first = (await client.post("/api/placement/attempts", json={})).json()["data"]
    second = (await client.post("/api/placement/attempts", json={})).json()["data"]
    assert first["id"] == second["id"]


async def test_items_are_withheld_until_the_timer_is_running(client, published, student):
    """The paper is released only once the clock starts.

    Acknowledging the instructions is the screen *before* the sitting. If the
    API handed the questions over there, anyone calling it directly could read
    all thirty untimed and then start the clock, and the time limit would mean
    nothing.
    """
    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]

    detail = (await client.get(f"/api/placement/attempts/{attempt['id']}")).json()["data"]
    assert detail["items"] == []

    await client.post(f"/api/placement/attempts/{attempt['id']}/confirm-eligibility")
    detail = (await client.get(f"/api/placement/attempts/{attempt['id']}")).json()["data"]
    assert detail["items"] == []

    await client.post(f"/api/placement/attempts/{attempt['id']}/acknowledge-instructions")
    detail = (await client.get(f"/api/placement/attempts/{attempt['id']}")).json()["data"]
    assert detail["state"] == "instructions_acknowledged"
    assert detail["items"] == [], "the paper must not be readable before the timer"

    await client.post(f"/api/placement/attempts/{attempt['id']}/begin")
    detail = (await client.get(f"/api/placement/attempts/{attempt['id']}")).json()["data"]
    assert detail["state"] == "in_progress"
    assert len(detail["items"]) == 30


async def test_audio_is_reported_unavailable_until_a_form_has_a_manifest(
    client, published, student
):
    """No approved recordings yet, so the client must not offer a play control.

    The package is explicit that a proctor reads each script twice until CLE
    approves audio. A play button that produces silence costs a learner their
    own exam minutes working out that nothing is broken.
    """
    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]
    assert attempt["audio_available"] is False


async def test_audio_is_reported_available_once_a_manifest_exists(
    client, published, db_session, student
):
    forms = (
        await db_session.execute(
            select(PlacementForm).where(PlacementForm.test_version_id == published.id)
        )
    ).scalars().all()
    for form in forms:
        form.audio_manifest = {"1": "https://example.invalid/a.mp3"}
    await db_session.commit()

    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]
    assert attempt["audio_available"] is True


async def test_the_delivered_payload_contains_no_restricted_field(
    client, published, student
):
    """The security assertion this whole design exists for.

    Checked as raw text, not by field name: a key leaking under any key name,
    or embedded in a nested blob, still fails.
    """
    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]
    await client.post(f"/api/placement/attempts/{attempt['id']}/confirm-eligibility")
    await client.post(f"/api/placement/attempts/{attempt['id']}/acknowledge-instructions")

    response = await client.get(f"/api/placement/attempts/{attempt['id']}")
    body = response.text
    payload = response.json()["data"]

    for forbidden in (
        "correct_answer", "answer_text", "rationale", "transcript",
        "legacy_band", "external_item_id", "slot", "target_vocabulary",
        "qa_status", "teacher_flags",
        # v1.3's teacher re-review ledger. `evidence_excerpt` quotes the item
        # and the rubric says where it is considered weak, so it is restricted
        # in the same way a key is.
        "teacher_review", "evidence_excerpt", "rubric_total", "candidate_status",
    ):
        assert forbidden not in body, f"{forbidden} leaked into the student payload"

    for item in payload["items"]:
        assert set(item) == {
            "id", "question_number", "section", "response_format", "option_letters",
            "expected_seconds", "audio_playback", "passage", "stem", "prompt", "options",
        }


async def test_a_student_cannot_read_another_students_attempt(
    client, published, db_session, student, instructor
):
    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]

    other = User(
        better_auth_id="placement_student_2",
        email="other.student@connect.ust.hk",
        full_name="Other Student",
        role="student",
    )
    db_session.add(other)
    await db_session.commit()

    _as(other)
    # 404, not 403: a 403 would confirm the attempt exists.
    response = await client.get(f"/api/placement/attempts/{attempt['id']}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Answering
# ---------------------------------------------------------------------------


async def _begin(client, student) -> dict:
    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]
    await client.post(f"/api/placement/attempts/{attempt['id']}/confirm-eligibility")
    await client.post(f"/api/placement/attempts/{attempt['id']}/acknowledge-instructions")
    await client.post(f"/api/placement/attempts/{attempt['id']}/begin")
    detail = (await client.get(f"/api/placement/attempts/{attempt['id']}")).json()["data"]
    return detail


async def test_answers_cannot_be_saved_before_the_timer_starts(
    client, published, db_session, student
):
    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]
    await client.post(f"/api/placement/attempts/{attempt['id']}/confirm-eligibility")
    await client.post(f"/api/placement/attempts/{attempt['id']}/acknowledge-instructions")

    # The item id comes from the database, not the API: the API deliberately
    # will not hand out the paper before the clock starts, so a caller guessing
    # an id is exactly the attack this endpoint has to refuse.
    row = await db_session.get(PlacementAttempt, uuid.UUID(attempt["id"]))
    item = (
        await db_session.execute(
            select(PlacementItem)
            .where(PlacementItem.form_id == row.form_id)
            .order_by(PlacementItem.question_number)
            .limit(1)
        )
    ).scalar_one()

    response = await client.put(
        f"/api/placement/attempts/{attempt['id']}/responses",
        json={"item_id": str(item.id), "response": "A"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ATTEMPT_NOT_EDITABLE"


async def test_saving_an_answer_is_idempotent_on_change_count(
    client, published, student
):
    detail = await _begin(client, student)
    item = detail["items"][0]

    for _ in range(3):
        response = await client.put(
            f"/api/placement/attempts/{detail['id']}/responses",
            json={"item_id": item["id"], "response": "A"},
        )
        assert response.status_code == 200
    assert response.json()["data"]["change_count"] == 0

    response = await client.put(
        f"/api/placement/attempts/{detail['id']}/responses",
        json={"item_id": item["id"], "response": "B"},
    )
    assert response.json()["data"]["change_count"] == 1


async def test_an_option_the_item_does_not_offer_is_rejected(
    client, published, student
):
    detail = await _begin(client, student)
    item = next(i for i in detail["items"] if i["response_format"] != "sequence")
    response = await client.put(
        f"/api/placement/attempts/{detail['id']}/responses",
        json={"item_id": item["id"], "response": "Z"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_RESPONSE"


async def test_an_ordering_item_requires_a_full_permutation(
    client, published, student
):
    detail = await _begin(client, student)
    sequence = next(i for i in detail["items"] if i["response_format"] == "sequence")

    bad = await client.put(
        f"/api/placement/attempts/{detail['id']}/responses",
        json={"item_id": sequence["id"], "response": "A"},
    )
    assert bad.status_code == 422

    repeated = await client.put(
        f"/api/placement/attempts/{detail['id']}/responses",
        json={"item_id": sequence["id"], "response": "A-A-B"},
    )
    assert repeated.status_code == 422

    good = await client.put(
        f"/api/placement/attempts/{detail['id']}/responses",
        json={"item_id": sequence["id"], "response": "c-a-b"},
    )
    assert good.status_code == 200
    assert good.json()["data"]["response"] == "C-A-B"


async def test_an_item_from_another_form_is_rejected(
    client, published, db_session, student
):
    detail = await _begin(client, student)
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    foreign = (
        await db_session.execute(
            select(PlacementItem).where(PlacementItem.form_id != attempt.form_id).limit(1)
        )
    ).scalar_one()

    response = await client.put(
        f"/api/placement/attempts/{detail['id']}/responses",
        json={"item_id": str(foreign.id), "response": "A"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Submission and review
# ---------------------------------------------------------------------------


async def _answer_all(client, db_session, detail: dict, *, correct: bool = True) -> None:
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    keys = {
        str(row.item_id): row.correct_answer
        for row in (
            await db_session.execute(
                select(PlacementItemKey.item_id, PlacementItemKey.correct_answer)
                .join(PlacementItem, PlacementItem.id == PlacementItemKey.item_id)
                .where(PlacementItem.form_id == attempt.form_id)
            )
        ).all()
    }
    for item in detail["items"]:
        key = keys[item["id"]]
        if correct:
            value = key
        elif item["response_format"] == "sequence":
            letters = item["option_letters"]
            value = "-".join(reversed(letters)) if list(reversed(letters)) != list(
                key.split("-")
            ) else "-".join(letters)
        else:
            value = next(
                letter for letter in item["option_letters"] if letter != key
            )
        await client.put(
            f"/api/placement/attempts/{detail['id']}/responses",
            json={"item_id": item["id"], "response": value, "time_spent_ms": 30_000},
        )


async def test_a_submitted_attempt_shows_pending_review_and_no_score(
    client, published, db_session, student
):
    """The learner sees a state, never a number, until CLE releases."""
    detail = await _begin(client, student)
    await _answer_all(client, db_session, detail)

    response = await client.post(f"/api/placement/attempts/{detail['id']}/submit")
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["released"] is False
    assert data["recommended_course"] is None
    assert "not an official HSK" in data["claim_limit"]
    assert "raw_score" not in response.text
    assert "band_scores" not in response.text


async def test_submitting_twice_is_rejected(client, published, db_session, student):
    detail = await _begin(client, student)
    await _answer_all(client, db_session, detail)

    assert (await client.post(f"/api/placement/attempts/{detail['id']}/submit")).status_code == 200
    second = await client.post(f"/api/placement/attempts/{detail['id']}/submit")
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ATTEMPT_NOT_SUBMITTABLE"


async def test_answers_are_locked_after_submission(
    client, published, db_session, student
):
    detail = await _begin(client, student)
    await _answer_all(client, db_session, detail)
    await client.post(f"/api/placement/attempts/{detail['id']}/submit")

    response = await client.put(
        f"/api/placement/attempts/{detail['id']}/responses",
        json={"item_id": detail["items"][0]["id"], "response": "A"},
    )
    assert response.status_code == 409


async def test_a_perfect_paper_is_scored_but_still_needs_release(
    client, published, db_session, student
):
    detail = await _begin(client, student)
    await _answer_all(client, db_session, detail)
    await client.post(f"/api/placement/attempts/{detail['id']}/submit")

    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    await db_session.refresh(attempt)
    assert attempt.raw_score == 30
    assert attempt.highest_sustained_band == 6
    assert attempt.provisional_course == "LANG1515"
    # Scored, not released. Nothing has reached the learner.
    assert attempt.state in {"scored", "review_pending"}
    assert attempt.released_at is None


async def test_scoring_pins_the_key_and_rule_versions(
    client, published, db_session, student
):
    detail = await _begin(client, student)
    await _answer_all(client, db_session, detail)
    await client.post(f"/api/placement/attempts/{detail['id']}/submit")

    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    await db_session.refresh(attempt)
    assert attempt.scored_key_version == published.key_version
    assert attempt.scored_rule_version == published.scoring_rule_version


async def test_an_interruption_routes_the_attempt_to_review(
    client, published, db_session, student
):
    detail = await _begin(client, student)
    await client.post(
        f"/api/placement/attempts/{detail['id']}/interruptions",
        json={"kind": "disconnect", "detail": "network dropped"},
    )
    await _answer_all(client, db_session, detail)
    await client.post(f"/api/placement/attempts/{detail['id']}/submit")

    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    await db_session.refresh(attempt)
    assert attempt.state == "review_pending"
    assert "technical_interruption" in attempt.review_flags
    assert attempt.confidence == "review"


# ---------------------------------------------------------------------------
# CLE review
# ---------------------------------------------------------------------------


async def _submitted_attempt(client, db_session, student) -> str:
    detail = await _begin(client, student)
    await _answer_all(client, db_session, detail)
    await client.post(f"/api/placement/attempts/{detail['id']}/submit")
    return detail["id"]


async def test_review_queue_is_instructor_only(client, published, student):
    _as(student)
    assert (await client.get("/api/placement/review/queue")).status_code == 403


async def test_review_queue_lists_the_submitted_attempt(
    client, published, db_session, student, instructor
):
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)

    data = (await client.get("/api/placement/review/queue")).json()["data"]
    assert any(i["attempt_id"] == attempt_id for i in data["items"])
    assert data["needs_review"] + data["ready_to_approve"] >= 1


async def test_evidence_bundle_exposes_keys_to_an_instructor(
    client, published, db_session, student, instructor
):
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)

    data = (
        await client.get(f"/api/placement/review/attempts/{attempt_id}")
    ).json()["data"]

    assert len(data["responses"]) == 30
    assert all(r["correct_answer"] for r in data["responses"])
    assert data["band_scores"] == {str(b): 5 for b in range(1, 7)}
    assert data["evidence_hash"]

    # v1.3: the reviewer is told why an item is in front of them, in the
    # content owner's own words, without opening the workbook.
    assert all(r["teacher_review"] for r in data["responses"])
    assert all(r["teacher_review"]["review_question"] for r in data["responses"])

    # Flag severity is resolved server-side, so the UI cannot disagree with the
    # publication gate about what counts as blocking.
    flagged = [r for r in data["responses"] if r["teacher_flags"]]
    assert flagged, "the v1.3 bank carries advisory content flags"
    assert all(
        flag["severity"] in {"blocking", "advisory"}
        for r in flagged
        for flag in r["teacher_flags"]
    )


async def test_evidence_bundle_is_not_reachable_by_a_student(
    client, published, db_session, student
):
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(student)
    response = await client.get(f"/api/placement/review/attempts/{attempt_id}")
    assert response.status_code == 403


async def test_approve_then_release_reaches_the_learner(
    client, published, db_session, student, instructor
):
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)

    approve = await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "approve"},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["data"]["state"] == "approved"

    release = await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "release"},
    )
    assert release.status_code == 200, release.text
    assert release.json()["data"]["state"] == "released"

    _as(student)
    result = (await client.get(f"/api/placement/attempts/{attempt_id}/result")).json()["data"]
    assert result["released"] is True
    assert result["recommended_course"] == "LANG1515"


async def test_a_result_cannot_be_released_without_a_decision(
    client, published, db_session, student, instructor
):
    """The single most important negative test in this file."""
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)

    response = await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "release"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RELEASE_NOT_APPROVED"

    _as(student)
    result = (await client.get(f"/api/placement/attempts/{attempt_id}/result")).json()["data"]
    assert result["released"] is False
    assert result["recommended_course"] is None


async def test_an_override_shows_the_reviewers_course_not_the_systems(
    client, published, db_session, student, instructor
):
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)

    await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={
            "action": "override",
            "final_course": "LANG1514",
            "reason_code": "course_fit",
            "reason_text": "Interview evidence suggests a better fit one level down.",
        },
    )
    await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "release"},
    )

    _as(student)
    result = (await client.get(f"/api/placement/attempts/{attempt_id}/result")).json()["data"]
    assert result["recommended_course"] == "LANG1514"


async def test_an_override_without_a_course_is_refused(
    client, published, db_session, student, instructor
):
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)
    response = await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "override", "reason_code": "course_fit"},
    )
    assert response.status_code == 422


async def test_a_non_approve_action_requires_a_reason_code(
    client, published, db_session, student, instructor
):
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)
    response = await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "request_advising"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "REASON_REQUIRED"


async def test_a_stale_evidence_hash_blocks_the_decision(
    client, published, db_session, student, instructor
):
    """A reviewer must not be recorded as deciding on evidence they never saw."""
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)
    response = await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "approve", "evidence_hash": "0" * 64},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EVIDENCE_STALE"


async def test_every_decision_is_audited(
    client, published, db_session, student, instructor
):
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)
    await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision", json={"action": "approve"})
    await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision", json={"action": "release"})

    events = (
        await db_session.execute(
            select(PlacementAuditEvent).where(
                PlacementAuditEvent.entity_id == uuid.UUID(attempt_id)
            )
        )
    ).scalars().all()
    types = {e.event_type for e in events}
    assert "placement.attempt.created" in types
    assert "placement.attempt.submitted" in types
    assert "placement.attempt.scored" in types
    assert "placement.review.approve" in types
    assert "placement.review.release" in types


# ---------------------------------------------------------------------------
# Attempt policy
# ---------------------------------------------------------------------------


async def test_a_second_attempt_gets_a_different_form(
    client, published, db_session, student
):
    first_id = await _submitted_attempt(client, db_session, student)
    first = await db_session.get(PlacementAttempt, uuid.UUID(first_id))

    _as(student)
    second = (await client.post("/api/placement/attempts", json={})).json()["data"]
    second_attempt = await db_session.get(PlacementAttempt, uuid.UUID(second["id"]))
    assert second_attempt.form_id != first.form_id
    assert second_attempt.attempt_number == 2


async def test_attempts_are_capped_at_the_version_maximum(
    client, published, db_session, student
):
    for _ in range(3):
        await _submitted_attempt(client, db_session, student)

    _as(student)
    response = await client.post("/api/placement/attempts", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ATTEMPTS_EXHAUSTED"


async def test_the_allocation_reference_records_why_a_form_was_chosen(
    client, published, db_session, student
):
    _as(student)
    data = (await client.post("/api/placement/attempts", json={})).json()["data"]
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(data["id"]))
    reference = attempt.allocation_reference
    assert reference["attempt_number"] == 1
    assert sorted(reference["eligible_forms"]) == ["A", "B", "C", "D", "E"]
    assert reference["selection"] == "uniform_random"


async def test_a_closed_window_refuses_a_new_attempt(
    client, published, db_session, student
):
    published.window_opens_at = datetime.now(timezone.utc) + timedelta(days=1)
    await db_session.commit()

    _as(student)
    response = await client.post("/api/placement/attempts", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "WINDOW_CLOSED"


# ---------------------------------------------------------------------------
# Expiry sweep
# ---------------------------------------------------------------------------


async def _expired_attempt(client, db_session, student, *, answers: int) -> PlacementAttempt:
    """An in-progress attempt whose timer has already run out."""
    detail = await _begin(client, student)
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))

    for item in detail["items"][:answers]:
        await client.put(
            f"/api/placement/attempts/{detail['id']}/responses",
            json={"item_id": item["id"], "response": item["option_letters"][0]},
        )

    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    attempt.started_at = past - timedelta(minutes=30)
    attempt.expires_at = past
    await db_session.commit()
    return attempt


async def test_an_expired_attempt_with_answers_is_submitted_and_scored(
    client, published, db_session, student
):
    """Running out of time must not throw away the work already done."""
    attempt = await _expired_attempt(client, db_session, student, answers=12)

    counts = await svc.sweep_stale_attempts(db_session)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert counts["submitted"] == 1
    assert attempt.state in {"scored", "review_pending"}
    assert attempt.raw_score is not None
    assert attempt.answered_count == 12
    # The reviewer is told why the record looks the way it does.
    assert "incomplete_answers" in attempt.review_flags
    assert any(e["kind"] == "timer_expired" for e in attempt.interruptions)


async def test_an_expired_attempt_with_no_answers_is_expired_not_scored(
    client, published, db_session, student
):
    """An empty paper has nothing to score; a band-0 result would be fiction."""
    attempt = await _expired_attempt(client, db_session, student, answers=0)

    counts = await svc.sweep_stale_attempts(db_session)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert counts["expired"] == 1
    assert attempt.state == "expired"
    assert attempt.raw_score is None


async def test_an_expiry_after_an_interruption_goes_to_technical_review(
    client, published, db_session, student
):
    """"The timer ran out" and "something broke" are not the same situation."""
    detail = await _begin(client, student)
    await client.post(
        f"/api/placement/attempts/{detail['id']}/interruptions",
        json={"kind": "disconnect"},
    )
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    attempt.started_at = datetime.now(timezone.utc) - timedelta(minutes=40)
    attempt.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.commit()

    counts = await svc.sweep_stale_attempts(db_session)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert counts["technical_review"] == 1
    assert attempt.state == "technical_review"


async def test_the_sweep_leaves_a_running_attempt_alone(
    client, published, db_session, student
):
    detail = await _begin(client, student)
    counts = await svc.sweep_stale_attempts(db_session)
    await db_session.commit()

    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    await db_session.refresh(attempt)
    assert attempt.state == "in_progress"
    assert not any(counts.values())


async def test_a_never_started_attempt_is_abandoned_without_costing_one(
    client, published, db_session, student
):
    """Clicking Start and walking away must not burn a third of the allowance.

    The paper is only released once the timer runs, so an attempt that never
    began gave the learner no information at all.
    """
    _as(student)
    created = (await client.post("/api/placement/attempts", json={})).json()["data"]
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(created["id"]))
    attempt.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
    await db_session.commit()

    counts = await svc.sweep_stale_attempts(db_session)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert counts["abandoned"] == 1
    assert attempt.state == "abandoned"

    # And they still have all three attempts.
    intro = (await client.get("/api/placement")).json()["data"]
    assert intro["attempts_remaining"] == 3


async def test_a_swept_attempt_frees_the_learner_to_start_again(
    client, published, db_session, student
):
    """The bug this sweep exists for: a dead attempt blocking every future one."""
    await _expired_attempt(client, db_session, student, answers=3)
    await svc.sweep_stale_attempts(db_session)
    await db_session.commit()

    _as(student)
    response = await client.post("/api/placement/attempts", json={})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["attempt_number"] == 2


async def test_the_sweep_is_audited(client, published, db_session, student):
    attempt = await _expired_attempt(client, db_session, student, answers=0)
    await svc.sweep_stale_attempts(db_session)
    await db_session.commit()

    events = (
        await db_session.execute(
            select(PlacementAuditEvent).where(
                PlacementAuditEvent.entity_id == attempt.id,
                PlacementAuditEvent.event_type.like("placement.attempt.swept.%"),
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].actor_role == "system"


# ---------------------------------------------------------------------------
# Listening audio delivery
# ---------------------------------------------------------------------------


async def _started_attempt(client, student):
    """Drive an attempt all the way to a running timer.

    ``/begin`` matters: items are released only in ``in_progress``, so stopping
    at the instructions screen yields an empty item list and any test that
    iterates it passes vacuously.
    """
    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]
    await client.post(f"/api/placement/attempts/{attempt['id']}/confirm-eligibility")
    await client.post(f"/api/placement/attempts/{attempt['id']}/acknowledge-instructions")
    await client.post(f"/api/placement/attempts/{attempt['id']}/begin")
    detail = (await client.get(f"/api/placement/attempts/{attempt['id']}")).json()["data"]
    assert detail["items"], "no items delivered; attempt did not reach in_progress"
    return attempt, detail


async def _publish_audio(db_session, published, *, monkeypatch=None):
    """Give every form a manifest, as a real generation run would."""
    forms = (
        await db_session.execute(
            select(PlacementForm).where(PlacementForm.test_version_id == published.id)
        )
    ).scalars().all()
    for form in forms:
        form.audio_manifest = {
            str(q): {"r2_key": f"placement/v/{form.form_code}/q{q:02d}.mp3"}
            for q in range(1, 13)
        }
    await db_session.commit()


async def test_audio_play_is_refused_when_no_recording_is_published(
    client, published, student
):
    """An empty manifest must not be a 500 or a silent success."""
    attempt, detail = await _started_attempt(client, student)
    listening = next(i for i in detail["items"] if i["section"] == "listening")
    resp = await client.post(
        f"/api/placement/attempts/{attempt['id']}/items/{listening['id']}/audio"
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "AUDIO_NOT_AVAILABLE"


async def test_audio_play_count_is_enforced_server_side(
    client, published, db_session, student, monkeypatch
):
    """The exam says a script is heard once or twice. The client cannot be
    trusted to stop at that, so the server must."""
    monkeypatch.setattr(
        "app.services.storage.generate_presigned_url",
        lambda key, expiration=300: f"https://signed.invalid/{key}?e={expiration}",
    )
    await _publish_audio(db_session, published)
    attempt, detail = await _started_attempt(client, student)
    listening = next(i for i in detail["items"] if i["section"] == "listening")
    allowed = listening["audio_playback"]
    assert allowed >= 1

    for expected in range(1, allowed + 1):
        resp = await client.post(
            f"/api/placement/attempts/{attempt['id']}/items/{listening['id']}/audio"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["plays_used"] == expected
        assert body["plays_allowed"] == allowed
        assert body["url"].startswith("https://signed.invalid/")

    exhausted = await client.post(
        f"/api/placement/attempts/{attempt['id']}/items/{listening['id']}/audio"
    )
    assert exhausted.status_code == 409
    assert exhausted.json()["detail"]["code"] == "AUDIO_PLAYS_EXHAUSTED"


async def test_audio_grant_leaks_no_transcript(
    client, published, db_session, student, monkeypatch
):
    """The audio is the delivery surface; the script stays restricted."""
    monkeypatch.setattr(
        "app.services.storage.generate_presigned_url",
        lambda key, expiration=300: f"https://signed.invalid/{key}",
    )
    await _publish_audio(db_session, published)
    attempt, detail = await _started_attempt(client, student)
    listening = next(i for i in detail["items"] if i["section"] == "listening")
    key_row = (
        await db_session.execute(
            select(PlacementItemKey).where(
                PlacementItemKey.item_id == uuid.UUID(listening["id"])
            )
        )
    ).scalar_one()

    body = (
        await client.post(
            f"/api/placement/attempts/{attempt['id']}/items/{listening['id']}/audio"
        )
    ).text
    assert key_row.transcript
    for line in key_row.transcript.split("\n"):
        assert line.strip() not in body

    # The key itself is a bare letter, so substring-searching the body for it
    # only ever proves that JSON contains the letter "A". Assert on the shape
    # instead: the grant carries these four fields and nothing else, so no
    # restricted value can ride along under any name.
    payload = json.loads(body)["data"]
    assert set(payload) == {"url", "plays_used", "plays_allowed", "expires_in_seconds"}


async def test_audio_play_is_refused_on_a_non_listening_item(
    client, published, db_session, student
):
    await _publish_audio(db_session, published)
    attempt, detail = await _started_attempt(client, student)
    reading = next(i for i in detail["items"] if i["section"] == "reading")
    resp = await client.post(
        f"/api/placement/attempts/{attempt['id']}/items/{reading['id']}/audio"
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "ITEM_HAS_NO_AUDIO"


async def test_another_learners_attempt_cannot_be_played(
    client, published, db_session, student, instructor
):
    await _publish_audio(db_session, published)
    attempt, detail = await _started_attempt(client, student)
    listening = next(i for i in detail["items"] if i["section"] == "listening")
    _as(instructor)
    resp = await client.post(
        f"/api/placement/attempts/{attempt['id']}/items/{listening['id']}/audio"
    )
    assert resp.status_code == 404
