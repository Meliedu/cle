"""Regressions found by the four-way review of the placement subsystem.

Each test here corresponds to a defect that was reachable in shipped code. They
are separated from the main suite so it is obvious what they are: not coverage
for its own sake, but a fence around specific ways this subsystem hurt someone.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.placement import PlacementAttempt
from app.services import placement as svc

from tests.test_placement_api import (  # noqa: F401  (fixtures)
    _as,
    _begin,
    _bearer,
    _submitted_attempt,
    instructor,
    published,
    student,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Attempt numbering: the worst defect found. A learner locked out permanently.
# ---------------------------------------------------------------------------


async def test_an_invalidated_attempt_does_not_lock_the_learner_out(
    client, published, db_session, student, instructor
):
    """Numbering came from the *consuming* list; the index counts *all* rows.

    So an invalidated attempt left its number behind and every later Start
    collided with it, 409'd, and did so forever. Invalidation is the remedy the
    code's own error messages recommend, which made it worse.
    """
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)
    invalidate = await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "invalidate", "reason_code": "technical_issue"},
    )
    assert invalidate.status_code == 200, invalidate.text

    _as(student)
    response = await client.post("/api/placement/attempts", json={})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["attempt_number"] == 2

    # And it gave the allowance back rather than consuming it.
    intro = (await client.get("/api/placement")).json()["data"]
    assert intro["attempts_remaining"] == 3


async def test_an_abandoned_attempt_does_not_lock_the_learner_out(
    client, published, db_session, student
):
    """The same collision, reachable with no operator involved at all.

    Click Start, close the tab, come back tomorrow.
    """
    _as(student)
    first = (await client.post("/api/placement/attempts", json={})).json()["data"]
    row = await db_session.get(PlacementAttempt, uuid.UUID(first["id"]))
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
    await db_session.commit()

    await svc.sweep_stale_attempts(db_session)
    await db_session.commit()

    response = await client.post("/api/placement/attempts", json={})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["attempt_number"] == 2


async def test_a_retake_never_re_serves_a_form_already_sat(
    client, published, db_session, student, instructor
):
    """Invalidation returns the allowance; it does not un-read the paper."""
    attempt_id = await _submitted_attempt(client, db_session, student)
    first = await db_session.get(PlacementAttempt, uuid.UUID(attempt_id))
    first_form = first.form_id

    _as(instructor)
    await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "invalidate", "reason_code": "technical_issue"},
    )

    _as(student)
    second = (await client.post("/api/placement/attempts", json={})).json()["data"]
    row = await db_session.get(PlacementAttempt, uuid.UUID(second["id"]))
    assert row.form_id != first_form


# ---------------------------------------------------------------------------
# Accommodation: authority-bearing, and it was learner-supplied.
# ---------------------------------------------------------------------------


async def test_a_student_cannot_grant_themselves_extra_time(
    client, published, db_session, student
):
    """It extended the deadline AND muted the flag that would have caught it."""
    _as(student)
    response = await client.post(
        "/api/placement/attempts",
        json={"accommodation": {"extended_time": True, "extra_minutes": 100000}},
    )
    assert response.status_code == 200, response.text
    attempt = await db_session.get(
        PlacementAttempt, uuid.UUID(response.json()["data"]["id"])
    )
    assert attempt.accommodation is None

    for step in ("confirm-eligibility", "acknowledge-instructions", "begin"):
        await client.post(f"/api/placement/attempts/{attempt.id}/{step}")
    await db_session.refresh(attempt)

    granted = (attempt.expires_at - attempt.started_at).total_seconds() / 60
    assert round(granted) == published.duration_minutes


async def test_a_granted_accommodation_is_capped(
    client, published, db_session, student
):
    _as(student)
    created = (await client.post("/api/placement/attempts", json={})).json()["data"]
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(created["id"]))
    attempt.accommodation = {"extended_time": True, "extra_minutes": 10**9}
    await db_session.commit()

    for step in ("confirm-eligibility", "acknowledge-instructions", "begin"):
        await client.post(f"/api/placement/attempts/{attempt.id}/{step}")
    await db_session.refresh(attempt)

    granted = (attempt.expires_at - attempt.started_at).total_seconds() / 60
    assert granted == published.duration_minutes + svc.MAX_EXTRA_MINUTES


async def test_a_malformed_accommodation_does_not_500(
    client, published, db_session, student
):
    _as(student)
    created = (await client.post("/api/placement/attempts", json={})).json()["data"]
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(created["id"]))
    attempt.accommodation = {"extended_time": True, "extra_minutes": "not a number"}
    await db_session.commit()

    for step in ("confirm-eligibility", "acknowledge-instructions"):
        await client.post(f"/api/placement/attempts/{attempt.id}/{step}")
    response = await client.post(f"/api/placement/attempts/{attempt.id}/begin")
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Review integrity
# ---------------------------------------------------------------------------


async def test_a_blocked_attempt_cannot_be_approved_by_a_direct_post(
    client, published, db_session, student, instructor
):
    """The rule was enforced only by a disabled button in the browser."""
    attempt_id = await _submitted_attempt(client, db_session, student)
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(attempt_id))
    attempt.review_flags = [*attempt.review_flags, "item_key_disputed"]
    await db_session.commit()

    _as(instructor)
    response = await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "approve"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BLOCKED_BY_CONTENT"

    # Invalidation stays available, because that is the way out.
    ok = await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "invalidate", "reason_code": "evidence_mismatch"},
    )
    assert ok.status_code == 200, ok.text


async def test_a_learner_cannot_append_interruptions_after_submitting(
    client, published, db_session, student
):
    """Each append changed the evidence hash, 409ing the reviewer forever."""
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(student)
    response = await client.post(
        f"/api/placement/attempts/{attempt_id}/interruptions",
        json={"kind": "disconnect"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ATTEMPT_NOT_EDITABLE"


async def test_interruptions_are_capped(client, published, db_session, student):
    detail = await _begin(client, student)
    for _ in range(svc.MAX_INTERRUPTIONS + 5):
        await client.post(
            f"/api/placement/attempts/{detail['id']}/interruptions",
            json={"kind": "disconnect"},
        )
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    await db_session.refresh(attempt)
    assert len(attempt.interruptions) == svc.MAX_INTERRUPTIONS


async def test_a_technical_review_attempt_can_return_to_normal_review(
    client, published, db_session, student, instructor
):
    """It was a trap: the only legal exit was the one that locked the learner out."""
    detail = await _begin(client, student)
    await client.post(
        f"/api/placement/attempts/{detail['id']}/interruptions",
        json={"kind": "disconnect"},
    )
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    attempt.started_at = datetime.now(timezone.utc) - timedelta(minutes=40)
    attempt.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.commit()

    await svc.sweep_stale_attempts(db_session)
    await db_session.commit()
    await db_session.refresh(attempt)
    assert attempt.state == "technical_review"

    _as(instructor)
    response = await client.post(
        f"/api/placement/review/attempts/{attempt.id}/decision",
        json={"action": "resume_review", "reason_code": "technical_issue"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "review_pending"


async def test_an_approved_attempt_stays_in_the_queue_until_released(
    client, published, db_session, student, instructor
):
    """It used to vanish, and the learner polled the pending screen forever."""
    attempt_id = await _submitted_attempt(client, db_session, student)
    _as(instructor)
    await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "approve"},
    )

    data = (await client.get("/api/placement/review/queue")).json()["data"]
    assert any(i["attempt_id"] == attempt_id for i in data["items"])
    assert data["ready_to_approve"] >= 1

    await client.post(
        f"/api/placement/review/attempts/{attempt_id}/decision",
        json={"action": "release"},
    )
    after = (await client.get("/api/placement/review/queue")).json()["data"]
    assert not any(i["attempt_id"] == attempt_id for i in after["items"])


# ---------------------------------------------------------------------------
# Evidence integrity
# ---------------------------------------------------------------------------


async def test_a_timer_expiry_is_not_reported_as_a_technical_interruption(
    client, published, db_session, student
):
    """The sweep records its own marker; counting it corrupts the evidence."""
    detail = await _begin(client, student)
    for item in detail["items"][:20]:
        await client.put(
            f"/api/placement/attempts/{detail['id']}/responses",
            json={"item_id": item["id"], "response": item["option_letters"][0]},
        )
    attempt = await db_session.get(PlacementAttempt, uuid.UUID(detail["id"]))
    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    attempt.started_at = past - timedelta(minutes=30)
    attempt.expires_at = past
    await db_session.commit()

    await svc.sweep_stale_attempts(db_session)
    await db_session.commit()
    await db_session.refresh(attempt)

    assert any(e["kind"] == "timer_expired" for e in attempt.interruptions)
    assert "technical_interruption" not in attempt.review_flags


async def test_an_approved_accommodation_does_not_produce_an_unexplained_review(
    client, published, db_session, student
):
    """The exemption suppressed the flag but not the confidence.

    So the learner landed in review with an EMPTY flag list, and the reviewer's
    "why this needs review" panel rendered nothing at all.
    """
    from app.services.placement_scoring import ScoredResponse, score_attempt

    responses = [
        ScoredResponse(
            question_number=i + 1,
            legacy_band=(i // 5) + 1,
            section="reading",
            response="A",
            correct_answer="A",
        )
        for i in range(30)
    ]
    result = score_attempt(
        responses,
        duration_seconds=60 * 60,
        accommodation={"extended_time": True},
    )
    assert "duration_too_long" not in result.review_flags
    # The point: no flag AND no unexplained review.
    assert result.confidence != "review" or result.review_flags


async def test_an_unbounded_response_field_does_not_500(
    client, published, db_session, student
):
    """One unprivileged request could poison the session on a timed exam.

    `ge=0` with no upper bound let a value above int4 range through Pydantic,
    and the INSERT then raised out of the route as an uncaught DataError.
    """
    detail = await _begin(client, student)
    response = await client.put(
        f"/api/placement/attempts/{detail['id']}/responses",
        json={
            "item_id": detail["items"][0]["id"],
            "response": "A",
            "time_spent_ms": 3_000_000_000,
        },
    )
    # Rejected as invalid input, not a server error.
    assert response.status_code == 422, response.text

    # And the endpoint still works afterwards, i.e. nothing was poisoned.
    ok = await client.put(
        f"/api/placement/attempts/{detail['id']}/responses",
        json={"item_id": detail["items"][0]["id"], "response": "A"},
    )
    assert ok.status_code == 200, ok.text


async def test_reported_item_time_exceeding_the_sitting_is_flagged():
    """Per-item timing is client-reported; the wall clock is not.

    Inflating it muted the fast-item half of the response-pattern trigger. The
    total cannot exceed the sitting, and the sitting is timed server-side, so
    the inconsistency is detectable even though the numbers are not trustworthy.
    """
    from app.services.placement_scoring import ScoredResponse, score_attempt

    inflated = [
        ScoredResponse(
            question_number=i + 1,
            legacy_band=(i // 5) + 1,
            section="reading",
            response="A",
            correct_answer="A",
            time_spent_ms=999_999,
        )
        for i in range(30)
    ]
    result = score_attempt(inflated, duration_seconds=30 * 60)
    assert "timing_inconsistent" in result.review_flags
    assert result.confidence == "review"


async def test_honest_item_timing_is_not_flagged():
    from app.services.placement_scoring import ScoredResponse, score_attempt

    honest = [
        ScoredResponse(
            question_number=i + 1,
            legacy_band=(i // 5) + 1,
            section="reading",
            response=chr(65 + i % 4),
            correct_answer="A",
            time_spent_ms=30_000,
        )
        for i in range(30)
    ]
    result = score_attempt(honest, duration_seconds=30 * 60)
    assert "timing_inconsistent" not in result.review_flags
