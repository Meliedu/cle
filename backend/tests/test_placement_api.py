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
    PlacementResponse,
    PlacementTestVersion,
)
from app.models.user import User
from app.services import placement as svc
from app.services import placement_bank

BANK_PATH = (
    Path(__file__).resolve().parents[1]
    / "app" / "data" / "placement" / "meli-placement-v1.2.json"
)

pytestmark = pytest.mark.asyncio


def _bank() -> dict:
    if not BANK_PATH.exists():  # pragma: no cover
        pytest.skip("item bank not generated")
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _clean_bank() -> dict:
    """The real bank with the teacher's blocking flags cleared.

    Used wherever a test needs a *publishable* version. The flags themselves are
    tested separately; here they would just prevent every other assertion.
    """
    bank = _bank()
    for form in bank["forms"]:
        for item in form["items"]:
            item["teacher_flags"] = []
            # Form B Q17's blank is numbered (13); it is the same defect and
            # would fail the key/prompt consistency preflight for a clean run.
            if item["safe"].get("prompt"):
                item["safe"]["prompt"] = (
                    f"请选择最合适的一项填入第（{item['question_number']}）空。"
                )
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
        db_session, _clean_bank(), scoring_rule_version="v1.2-candidate"
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
        db_session, _bank(), scoring_rule_version="v1.2-candidate"
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
        db_session, _bank(), scoring_rule_version="v1.2-candidate"
    )
    await db_session.commit()
    assert version.status == "candidate"


async def test_importing_the_same_version_twice_is_refused(db_session):
    await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version="v1.2-candidate"
    )
    await db_session.commit()
    with pytest.raises(placement_bank.PlacementBankError) as excinfo:
        await placement_bank.import_bank(
            db_session, _bank(), scoring_rule_version="v1.2-candidate"
        )
    assert excinfo.value.code == "VERSION_EXISTS"


async def test_preflight_blocks_publication_on_the_teacher_disputed_keys(db_session):
    """The real v1.2 package must NOT be publishable as shipped.

    Two items carry a teacher's report that the key is wrong or ambiguous.
    Scoring either would produce a number nobody can defend, so the gate holds.
    """
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version="v1.2-candidate"
    )
    await db_session.commit()

    result = await placement_bank.preflight_version(db_session, version)
    assert result.can_publish is False
    codes = {f.code for f in result.blocking}
    assert "key_disputed" in codes
    disputed_items = {f.external_item_id for f in result.blocking if f.code == "key_disputed"}
    assert disputed_items == {"HSK5-B-13", "HSK3-C-12"}


async def test_publish_endpoint_refuses_a_version_with_blocking_findings(
    client, db_session, instructor
):
    version = await placement_bank.import_bank(
        db_session, _bank(), scoring_rule_version="v1.2-candidate"
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
        db_session, _clean_bank(), scoring_rule_version="v1.2-candidate"
    )
    await db_session.commit()
    _as(instructor)

    response = await client.post(f"/api/placement/versions/{version.id}/publish")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "published"


async def test_publishing_is_audited(client, db_session, instructor):
    version = await placement_bank.import_bank(
        db_session, _clean_bank(), scoring_rule_version="v1.2-candidate"
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
        db_session, _clean_bank(), scoring_rule_version="v1.2-candidate"
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


async def test_items_are_withheld_until_instructions_are_acknowledged(
    client, published, student
):
    """Handing out the paper before the sitting would let it be read for free."""
    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]

    detail = (await client.get(f"/api/placement/attempts/{attempt['id']}")).json()["data"]
    assert detail["items"] == []

    await client.post(f"/api/placement/attempts/{attempt['id']}/confirm-eligibility")
    await client.post(f"/api/placement/attempts/{attempt['id']}/acknowledge-instructions")

    detail = (await client.get(f"/api/placement/attempts/{attempt['id']}")).json()["data"]
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
    client, published, student
):
    _as(student)
    attempt = (await client.post("/api/placement/attempts", json={})).json()["data"]
    await client.post(f"/api/placement/attempts/{attempt['id']}/confirm-eligibility")
    await client.post(f"/api/placement/attempts/{attempt['id']}/acknowledge-instructions")
    detail = (await client.get(f"/api/placement/attempts/{attempt['id']}")).json()["data"]

    response = await client.put(
        f"/api/placement/attempts/{attempt['id']}/responses",
        json={"item_id": detail["items"][0]["id"], "response": "A"},
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
