"""Placement attempt lifecycle: allocate, deliver, save, submit, score, review.

Everything that touches a learner's attempt goes through here so the invariants
live in one place:

* a learner never receives a key, a transcript, a rationale or a band label;
* an answer can only change while the attempt is ``in_progress`` and inside its
  window;
* submission is atomic and one-way;
* scoring pins the key and rule versions it used;
* nothing reaches the learner as a recommendation without a CLE release.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.placement import (
    PlacementAttempt,
    PlacementAuditEvent,
    PlacementForm,
    PlacementItem,
    PlacementItemKey,
    PlacementResponse,
    PlacementReview,
    PlacementTestVersion,
)
from app.models.user import User
from app.services import placement_bank, placement_scoring, placement_state
from app.services.placement_scoring import ScoredResponse, ScoringPolicy
from app.services.placement_state import PlacementStateError

#: Grace beyond the published duration before the server stops accepting saves.
#: A learner whose last answer lands two seconds after the timer should not lose
#: it to clock skew; a learner still answering ten minutes later should.
SUBMIT_GRACE_SECONDS = 120


class PlacementError(Exception):
    """Typed placement error; the router maps ``code`` to a response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """Postgres may hand back a naive datetime depending on driver settings."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Version + form access
# ---------------------------------------------------------------------------


async def active_version(db: AsyncSession) -> PlacementTestVersion:
    """The single published version, or a typed error.

    A candidate version is deliberately not usable for delivery: candidate
    means CLE has not approved the content, and the whole point of the
    publication gate is that unapproved content cannot be sat.
    """
    version = (
        await db.execute(
            select(PlacementTestVersion).where(PlacementTestVersion.status == "published")
        )
    ).scalar_one_or_none()
    if version is None:
        raise PlacementError(
            "NO_PUBLISHED_VERSION",
            "no placement test version is currently published",
        )
    return version


def _window_open(version: PlacementTestVersion, at: datetime) -> bool:
    opens = _aware(version.window_opens_at)
    closes = _aware(version.window_closes_at)
    if opens is not None and at < opens:
        return False
    if closes is not None and at > closes:
        return False
    return True


# ---------------------------------------------------------------------------
# Attempt creation
# ---------------------------------------------------------------------------


async def _prior_attempts(
    db: AsyncSession, *, user_id: uuid.UUID, version_id: uuid.UUID
) -> Sequence[PlacementAttempt]:
    return (
        (
            await db.execute(
                select(PlacementAttempt)
                .where(
                    PlacementAttempt.user_id == user_id,
                    PlacementAttempt.test_version_id == version_id,
                )
                .order_by(PlacementAttempt.attempt_number)
            )
        )
        .scalars()
        .all()
    )


async def open_attempt(
    db: AsyncSession, *, user: User, version: PlacementTestVersion
) -> PlacementAttempt | None:
    """The learner's live attempt for this version, if any."""
    return (
        await db.execute(
            select(PlacementAttempt).where(
                PlacementAttempt.user_id == user.id,
                PlacementAttempt.test_version_id == version.id,
                PlacementAttempt.state.in_(
                    [
                        "created",
                        "eligibility_confirmed",
                        "instructions_acknowledged",
                        "in_progress",
                    ]
                ),
            )
        )
    ).scalar_one_or_none()


async def create_attempt(
    db: AsyncSession,
    *,
    user: User,
    declared_band: int | None = None,
    accommodation: Mapping[str, Any] | None = None,
) -> PlacementAttempt:
    """Start an attempt, allocating an unused form.

    Returns the existing live attempt if one exists rather than minting a
    second: resuming is the correct answer to "the learner pressed Start
    again", and the partial unique index makes that guarantee real even under a
    double-submit race.
    """
    version = await active_version(db)
    now = _now()

    if not _window_open(version, now):
        raise PlacementError(
            "WINDOW_CLOSED", "the placement test is not open at this time"
        )

    existing = await open_attempt(db, user=user, version=version)
    if existing is not None:
        return existing

    prior = await _prior_attempts(db, user_id=user.id, version_id=version.id)
    consuming = [
        attempt
        for attempt in prior
        if attempt.state in placement_state.CONSUMING_STATES
    ]
    if len(consuming) >= version.max_attempts:
        raise PlacementError(
            "ATTEMPTS_EXHAUSTED",
            f"this learner has used all {version.max_attempts} placement attempts",
        )

    forms = (
        (
            await db.execute(
                select(PlacementForm).where(PlacementForm.test_version_id == version.id)
            )
        )
        .scalars()
        .all()
    )
    try:
        allocation = placement_state.allocate_form(
            available=[
                {"form_code": form.form_code, "status": form.status} for form in forms
            ],
            # Only forms actually sat are excluded. An invalidated attempt's
            # form becomes available again, which is the point of invalidating.
            used_form_codes=[
                _form_code(forms, attempt.form_id)
                for attempt in consuming
            ],
            attempt_number=len(consuming) + 1,
        )
    except placement_state.FormRotationError as error:
        raise PlacementError(error.code, error.message) from error

    form = next(f for f in forms if f.form_code == allocation.form_code)

    attempt = PlacementAttempt(
        user_id=user.id,
        test_version_id=version.id,
        form_id=form.id,
        attempt_number=len(consuming) + 1,
        state="created",
        allocation_reference=allocation.reference,
        declared_band=declared_band,
        accommodation=dict(accommodation) if accommodation else None,
    )
    db.add(attempt)
    try:
        await db.flush()
    except IntegrityError as error:
        # Lost the race on uq_placement_attempts_single_open: the other request
        # already created the attempt, so resume that one.
        await db.rollback()
        resumed = await open_attempt(db, user=user, version=version)
        if resumed is None:
            raise PlacementError(
                "ATTEMPT_CONFLICT", "could not start a placement attempt"
            ) from error
        return resumed

    await record_audit(
        db,
        actor=user,
        actor_role="student",
        event_type="placement.attempt.created",
        entity_kind="placement_attempt",
        entity_id=attempt.id,
        metadata={
            "attempt_number": attempt.attempt_number,
            "form_code": form.form_code,
            "allocation": allocation.reference,
        },
    )
    return attempt


def _form_code(forms: Sequence[PlacementForm], form_id: uuid.UUID) -> str:
    for form in forms:
        if form.id == form_id:
            return form.form_code
    return ""


# ---------------------------------------------------------------------------
# Delivery (safe payload only)
# ---------------------------------------------------------------------------


async def delivery_items(
    db: AsyncSession, *, attempt: PlacementAttempt
) -> list[dict[str, Any]]:
    """The student-safe payload for an attempt's form.

    Selects explicitly from ``placement_items`` only. The keys live in a
    different table, so there is no column here that could leak one even if a
    future edit adds a careless join.
    """
    rows = (
        (
            await db.execute(
                select(PlacementItem)
                .where(
                    PlacementItem.form_id == attempt.form_id,
                    PlacementItem.is_active.is_(True),
                )
                .order_by(PlacementItem.question_number)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(item.id),
            "question_number": item.question_number,
            "section": item.section,
            "response_format": item.response_format,
            "option_letters": list(item.option_letters),
            "expected_seconds": item.expected_seconds,
            "audio_playback": item.audio_playback,
            "passage": item.passage,
            "stem": item.stem,
            "prompt": item.prompt,
            "options": list(item.options),
        }
        for item in rows
    ]


# ---------------------------------------------------------------------------
# Progression
# ---------------------------------------------------------------------------


async def advance(
    db: AsyncSession, *, attempt: PlacementAttempt, target: str, actor: User
) -> PlacementAttempt:
    """Move an attempt to ``target`` if the machine allows it."""
    placement_state.assert_transition(attempt.state, target)
    before = attempt.state
    attempt.state = target

    if target == "in_progress" and attempt.started_at is None:
        version = await db.get(PlacementTestVersion, attempt.test_version_id)
        started = _now()
        attempt.started_at = started
        minutes = version.duration_minutes if version else 30
        extra = 0
        if attempt.accommodation and attempt.accommodation.get("extended_time"):
            # Extra time is a granted accommodation, expressed in minutes so the
            # audit record shows exactly what was granted.
            extra = int(attempt.accommodation.get("extra_minutes", minutes))
        attempt.expires_at = started + timedelta(minutes=minutes + extra)

    await db.flush()
    await record_audit(
        db,
        actor=actor,
        actor_role=getattr(actor, "role", "student"),
        event_type=f"placement.attempt.{target}",
        entity_kind="placement_attempt",
        entity_id=attempt.id,
        metadata={"from": before, "to": target},
    )
    return attempt


# ---------------------------------------------------------------------------
# Saving answers
# ---------------------------------------------------------------------------


def _validate_response(item: PlacementItem, response: str | None) -> str | None:
    """Reject anything that is not a legal answer for this item.

    Blank is legal (a learner may clear an answer). Anything else must be a
    letter the item actually offers, or -- for an ordering item -- a permutation
    of exactly its letters.
    """
    if response is None or not response.strip():
        return None

    normalised = placement_scoring.normalise_response(response)
    letters = list(item.option_letters)

    if item.response_format == "sequence":
        if len(normalised) != len(letters) or sorted(normalised) != sorted(letters):
            raise PlacementError(
                "INVALID_RESPONSE",
                f"question {item.question_number} expects an order of "
                f"{len(letters)} distinct options",
            )
        return "-".join(normalised)

    if normalised not in letters:
        raise PlacementError(
            "INVALID_RESPONSE",
            f"question {item.question_number} has no option '{normalised}'",
        )
    return normalised


async def save_response(
    db: AsyncSession,
    *,
    attempt: PlacementAttempt,
    item_id: uuid.UUID,
    response: str | None,
    time_spent_ms: int | None = None,
    audio_play_count: int | None = None,
    connection_state: str | None = None,
) -> PlacementResponse:
    """Idempotently record one answer.

    Re-saving the same value is a no-op on ``change_count``: autosave retries
    and flaky connections must not look like a learner second-guessing
    themselves, since change count is review evidence.
    """
    if attempt.state not in placement_state.MUTABLE_STATES:
        raise PlacementError(
            "ATTEMPT_NOT_EDITABLE",
            "this attempt can no longer be changed",
        )

    expires = _aware(attempt.expires_at)
    if expires is not None and _now() > expires + timedelta(seconds=SUBMIT_GRACE_SECONDS):
        raise PlacementError("ATTEMPT_EXPIRED", "the time limit for this attempt has passed")

    item = await db.get(PlacementItem, item_id)
    if item is None or item.form_id != attempt.form_id:
        raise PlacementError("UNKNOWN_ITEM", "that question is not part of this attempt")

    value = _validate_response(item, response)

    existing = (
        await db.execute(
            select(PlacementResponse).where(
                PlacementResponse.attempt_id == attempt.id,
                PlacementResponse.item_id == item.id,
            )
        )
    ).scalar_one_or_none()

    now = _now()
    if existing is None:
        row = PlacementResponse(
            attempt_id=attempt.id,
            item_id=item.id,
            user_id=attempt.user_id,
            question_number=item.question_number,
            response=value,
            first_seen_at=now,
            answered_at=now if value else None,
            change_count=0,
            audio_play_count=audio_play_count or 0,
            time_spent_ms=time_spent_ms,
            connection_state=connection_state,
        )
        db.add(row)
        await db.flush()
        return row

    if existing.response != value:
        existing.change_count += 1
        existing.response = value
        existing.answered_at = now if value else None
    if time_spent_ms is not None:
        existing.time_spent_ms = time_spent_ms
    if audio_play_count is not None:
        # Monotonic: a reconnect must not lower a count the reviewer relies on.
        existing.audio_play_count = max(existing.audio_play_count, audio_play_count)
    if connection_state is not None:
        existing.connection_state = connection_state
    await db.flush()
    return existing


async def record_interruption(
    db: AsyncSession, *, attempt: PlacementAttempt, kind: str, detail: str | None = None
) -> None:
    """Append a technical event. Feeds the technical review trigger."""
    events = list(attempt.interruptions or [])
    events.append(
        {"kind": kind, "detail": detail, "at": _now().isoformat()}
    )
    attempt.interruptions = events
    await db.flush()


# ---------------------------------------------------------------------------
# Submission and scoring
# ---------------------------------------------------------------------------


async def submit_attempt(
    db: AsyncSession, *, attempt: PlacementAttempt, actor: User
) -> PlacementAttempt:
    """Close the attempt to further answers, then score it.

    Atomic and one-way: the state check plus the row update happen in the same
    transaction as scoring, so a duplicate submit finds the attempt already out
    of ``in_progress`` and is rejected rather than double-scoring.
    """
    if attempt.state != "in_progress":
        raise PlacementError(
            "ATTEMPT_NOT_SUBMITTABLE",
            "only an in-progress attempt can be submitted",
        )

    # Conditional update: whoever flips in_progress -> submitted first wins.
    result = await db.execute(
        update(PlacementAttempt)
        .where(
            PlacementAttempt.id == attempt.id,
            PlacementAttempt.state == "in_progress",
        )
        .values(state="submitted", submitted_at=_now())
        .returning(PlacementAttempt.id)
    )
    if result.scalar_one_or_none() is None:
        raise PlacementError(
            "ATTEMPT_NOT_SUBMITTABLE", "this attempt has already been submitted"
        )
    await db.refresh(attempt)

    started = _aware(attempt.started_at)
    submitted = _aware(attempt.submitted_at)
    if started and submitted:
        attempt.duration_seconds = int((submitted - started).total_seconds())

    await record_audit(
        db,
        actor=actor,
        actor_role="student",
        event_type="placement.attempt.submitted",
        entity_kind="placement_attempt",
        entity_id=attempt.id,
        metadata={"duration_seconds": attempt.duration_seconds},
    )

    return await score_attempt(db, attempt=attempt, actor=actor)


async def score_attempt(
    db: AsyncSession, *, attempt: PlacementAttempt, actor: User
) -> PlacementAttempt:
    """Compute band/skill evidence and the provisional recommendation."""
    version = await db.get(PlacementTestVersion, attempt.test_version_id)
    form = await db.get(PlacementForm, attempt.form_id)
    if version is None or form is None:  # pragma: no cover - FK guarantees these
        raise PlacementError("ATTEMPT_INCOMPLETE", "attempt is missing its version or form")

    disputed = await placement_bank.disputed_item_ids(db, version.id)

    rows = (
        await db.execute(
            select(
                PlacementItem.id,
                PlacementItem.question_number,
                PlacementItem.section,
                PlacementItemKey.legacy_band,
                PlacementItemKey.correct_answer,
                PlacementResponse.response,
                PlacementResponse.time_spent_ms,
            )
            .join(PlacementItemKey, PlacementItemKey.item_id == PlacementItem.id)
            .outerjoin(
                PlacementResponse,
                (PlacementResponse.item_id == PlacementItem.id)
                & (PlacementResponse.attempt_id == attempt.id),
            )
            .where(PlacementItem.form_id == attempt.form_id)
            .order_by(PlacementItem.question_number)
        )
    ).all()

    scored = [
        ScoredResponse(
            question_number=row.question_number,
            legacy_band=row.legacy_band,
            section=row.section,
            response=row.response,
            correct_answer=row.correct_answer,
            key_disputed=row.id in disputed,
            time_spent_ms=row.time_spent_ms,
        )
        for row in rows
    ]

    prior_bands = [
        a.highest_sustained_band
        for a in await _prior_attempts(
            db, user_id=attempt.user_id, version_id=version.id
        )
        if a.id != attempt.id
        and a.highest_sustained_band is not None
        and a.state not in {"invalidated", "abandoned", "expired"}
    ]

    policy = ScoringPolicy.from_config(version.review_policy)
    result = placement_scoring.score_attempt(
        scored,
        duration_seconds=attempt.duration_seconds,
        policy=policy,
        declared_band=attempt.declared_band,
        interruptions=list(attempt.interruptions or []),
        prior_attempt_bands=prior_bands,
        accommodation=attempt.accommodation,
        form_compromised=form.status == "compromised",
    )

    # Persist correctness now that keys are legitimately in scope.
    correctness = {
        row.id: placement_scoring.is_correct(row.response, row.correct_answer)
        and row.id not in disputed
        for row in rows
    }
    responses = (
        (
            await db.execute(
                select(PlacementResponse).where(PlacementResponse.attempt_id == attempt.id)
            )
        )
        .scalars()
        .all()
    )
    for response in responses:
        response.is_correct = correctness.get(response.item_id)

    attempt.raw_score = result.raw_score
    attempt.answered_count = result.answered_count
    attempt.band_scores = {str(k): v for k, v in result.band_scores.items()}
    attempt.skill_scores = result.skill_scores
    attempt.highest_sustained_band = result.highest_sustained_band
    attempt.provisional_course = result.provisional_course
    attempt.lower_band_break = result.lower_band_break
    attempt.clear_next_band_boundary = result.clear_next_band_boundary
    attempt.confidence = result.confidence
    attempt.review_flags = list(result.review_flags)
    attempt.scored_at = _now()
    attempt.scored_key_version = version.key_version
    attempt.scored_rule_version = version.scoring_rule_version

    placement_state.assert_transition(attempt.state, "scored")
    attempt.state = "scored"
    await db.flush()

    # A triggered attempt must land in review; this is not the caller's choice.
    target = placement_state.next_state_after_scoring(
        requires_review=result.requires_review
    )
    if target != attempt.state:
        placement_state.assert_transition(attempt.state, target)
        attempt.state = target
        await db.flush()

    await record_audit(
        db,
        actor=actor,
        actor_role=getattr(actor, "role", "system"),
        event_type="placement.attempt.scored",
        entity_kind="placement_attempt",
        entity_id=attempt.id,
        metadata={
            "raw_score": result.raw_score,
            "highest_sustained_band": result.highest_sustained_band,
            "provisional_course": result.provisional_course,
            "confidence": result.confidence,
            "review_flags": result.review_flags,
            "key_version": version.key_version,
            "rule_version": version.scoring_rule_version,
            "state": attempt.state,
        },
    )
    return attempt


# ---------------------------------------------------------------------------
# CLE review
# ---------------------------------------------------------------------------


ACTION_TO_STATE = {
    "approve": "approved",
    "override": "overridden",
    "request_advising": "advising_required",
    "invalidate": "invalidated",
}


async def record_decision(
    db: AsyncSession,
    *,
    attempt: PlacementAttempt,
    reviewer: User,
    action: str,
    final_course: str | None = None,
    reason_code: str | None = None,
    reason_text: str | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> PlacementReview:
    """Record a CLE decision and move the attempt accordingly.

    The reviewer's decision and the state change are one transaction: a review
    row without its transition, or a transition without its row, would each
    leave the audit trail lying about what happened.
    """
    if action not in ACTION_TO_STATE and action != "release":
        raise PlacementError("UNKNOWN_ACTION", f"unknown review action '{action}'")

    if action == "release":
        return await release_result(db, attempt=attempt, reviewer=reviewer, evidence=evidence)

    target = ACTION_TO_STATE[action]
    try:
        placement_state.assert_transition(attempt.state, target)
    except PlacementStateError as error:
        raise PlacementError(error.code, error.message) from error

    if action == "override" and not final_course:
        raise PlacementError(
            "OVERRIDE_NEEDS_COURSE", "an override must name the final course"
        )
    if action != "approve" and not reason_code:
        raise PlacementError(
            "REASON_REQUIRED", f"'{action}' requires a reason code"
        )

    review = PlacementReview(
        attempt_id=attempt.id,
        reviewer_id=reviewer.id,
        action=action,
        system_recommendation=attempt.provisional_course,
        final_course=final_course or (
            attempt.provisional_course if action == "approve" else None
        ),
        reason_code=reason_code,
        reason_text=reason_text,
        evidence_snapshot_hash=(
            placement_state.evidence_snapshot_hash(evidence) if evidence else None
        ),
    )
    db.add(review)

    before = attempt.state
    attempt.state = target
    await db.flush()

    await record_audit(
        db,
        actor=reviewer,
        actor_role="instructor",
        event_type=f"placement.review.{action}",
        entity_kind="placement_attempt",
        entity_id=attempt.id,
        metadata={
            "from": before,
            "to": target,
            "system_recommendation": attempt.provisional_course,
            "final_course": review.final_course,
            "reason_code": reason_code,
        },
    )
    return review


async def release_result(
    db: AsyncSession,
    *,
    attempt: PlacementAttempt,
    reviewer: User,
    evidence: Mapping[str, Any] | None = None,
) -> PlacementReview:
    """Unlock the recommendation for the learner. The only such path."""
    try:
        placement_state.assert_release_allowed(attempt.state)
        placement_state.assert_transition(attempt.state, "released")
    except PlacementStateError as error:
        raise PlacementError(error.code, error.message) from error

    latest = (
        await db.execute(
            select(PlacementReview)
            .where(PlacementReview.attempt_id == attempt.id)
            .order_by(PlacementReview.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    review = PlacementReview(
        attempt_id=attempt.id,
        reviewer_id=reviewer.id,
        action="release",
        system_recommendation=attempt.provisional_course,
        final_course=(latest.final_course if latest else attempt.provisional_course),
        evidence_snapshot_hash=(
            placement_state.evidence_snapshot_hash(evidence) if evidence else None
        ),
    )
    db.add(review)

    before = attempt.state
    attempt.state = "released"
    attempt.released_at = _now()
    await db.flush()

    await record_audit(
        db,
        actor=reviewer,
        actor_role="instructor",
        event_type="placement.review.release",
        entity_kind="placement_attempt",
        entity_id=attempt.id,
        metadata={"from": before, "final_course": review.final_course},
    )
    return review


async def released_course(db: AsyncSession, *, attempt: PlacementAttempt) -> str | None:
    """The course a learner may actually be shown, or ``None``.

    Reads the decision, never the provisional field: showing
    ``provisional_course`` after an override would display the number the
    reviewer rejected.
    """
    if attempt.state not in placement_state.RELEASED_STATES:
        return None
    review = (
        await db.execute(
            select(PlacementReview)
            .where(
                PlacementReview.attempt_id == attempt.id,
                PlacementReview.final_course.isnot(None),
            )
            .order_by(PlacementReview.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return review.final_course if review else None


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


async def record_audit(
    db: AsyncSession,
    *,
    actor: User | None,
    actor_role: str,
    event_type: str,
    entity_kind: str,
    entity_id: uuid.UUID,
    metadata: Mapping[str, Any] | None = None,
    request_id: str | None = None,
    before_hash: str | None = None,
    after_hash: str | None = None,
) -> None:
    """Append one audit row. Never raises into the caller's happy path."""
    db.add(
        PlacementAuditEvent(
            actor_id=actor.id if actor else None,
            actor_role=actor_role,
            event_type=event_type,
            entity_kind=entity_kind,
            entity_id=entity_id,
            before_hash=before_hash,
            after_hash=after_hash,
            request_id=request_id,
            event_metadata=dict(metadata) if metadata else None,
        )
    )


# ---------------------------------------------------------------------------
# Evidence bundle for the reviewer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttemptEvidence:
    attempt: PlacementAttempt
    form_code: str
    responses: list[dict[str, Any]]
    prior_attempts: list[dict[str, Any]]
    reviews: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": str(self.attempt.id),
            "state": self.attempt.state,
            "form_code": self.form_code,
            "raw_score": self.attempt.raw_score,
            "answered_count": self.attempt.answered_count,
            "band_scores": self.attempt.band_scores,
            "skill_scores": self.attempt.skill_scores,
            "highest_sustained_band": self.attempt.highest_sustained_band,
            "provisional_course": self.attempt.provisional_course,
            "lower_band_break": self.attempt.lower_band_break,
            "clear_next_band_boundary": self.attempt.clear_next_band_boundary,
            "confidence": self.attempt.confidence,
            "review_flags": list(self.attempt.review_flags or []),
            "duration_seconds": self.attempt.duration_seconds,
            "declared_band": self.attempt.declared_band,
            "interruptions": list(self.attempt.interruptions or []),
            "key_version": self.attempt.scored_key_version,
            "rule_version": self.attempt.scored_rule_version,
            "responses": self.responses,
            "prior_attempts": self.prior_attempts,
            "reviews": self.reviews,
        }


async def build_evidence(
    db: AsyncSession, *, attempt: PlacementAttempt
) -> AttemptEvidence:
    """Assemble everything a reviewer needs, including the keys.

    Instructor-only by construction: this is the one function that reads
    ``placement_item_keys`` alongside a learner's responses, and every caller
    sits behind ``require_instructor``.
    """
    form = await db.get(PlacementForm, attempt.form_id)

    rows = (
        await db.execute(
            select(
                PlacementItem.question_number,
                PlacementItem.section,
                PlacementItem.response_format,
                PlacementItemKey.legacy_band,
                PlacementItemKey.external_item_id,
                PlacementItemKey.correct_answer,
                PlacementItemKey.answer_text,
                PlacementItemKey.rationale,
                PlacementItemKey.teacher_flags,
                PlacementResponse.response,
                PlacementResponse.is_correct,
                PlacementResponse.change_count,
                PlacementResponse.time_spent_ms,
                PlacementResponse.audio_play_count,
            )
            .join(PlacementItemKey, PlacementItemKey.item_id == PlacementItem.id)
            .outerjoin(
                PlacementResponse,
                (PlacementResponse.item_id == PlacementItem.id)
                & (PlacementResponse.attempt_id == attempt.id),
            )
            .where(PlacementItem.form_id == attempt.form_id)
            .order_by(PlacementItem.question_number)
        )
    ).all()

    responses = [
        {
            "question_number": row.question_number,
            "section": row.section,
            "response_format": row.response_format,
            "legacy_band": row.legacy_band,
            "item_id": row.external_item_id,
            "correct_answer": row.correct_answer,
            "answer_text": row.answer_text,
            "rationale": row.rationale,
            "teacher_flags": list(row.teacher_flags or []),
            "response": row.response,
            "is_correct": row.is_correct,
            "change_count": row.change_count,
            "time_spent_ms": row.time_spent_ms,
            "audio_play_count": row.audio_play_count,
        }
        for row in rows
    ]

    prior = [
        {
            "attempt_id": str(a.id),
            "attempt_number": a.attempt_number,
            "state": a.state,
            "raw_score": a.raw_score,
            "highest_sustained_band": a.highest_sustained_band,
            "provisional_course": a.provisional_course,
            "confidence": a.confidence,
            "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
        }
        for a in await _prior_attempts(
            db, user_id=attempt.user_id, version_id=attempt.test_version_id
        )
        if a.id != attempt.id
    ]

    review_rows = (
        (
            await db.execute(
                select(PlacementReview)
                .where(PlacementReview.attempt_id == attempt.id)
                .order_by(PlacementReview.created_at)
            )
        )
        .scalars()
        .all()
    )
    reviews = [
        {
            "action": r.action,
            "system_recommendation": r.system_recommendation,
            "final_course": r.final_course,
            "reason_code": r.reason_code,
            "reason_text": r.reason_text,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in review_rows
    ]

    return AttemptEvidence(
        attempt=attempt,
        form_code=form.form_code if form else "",
        responses=responses,
        prior_attempts=prior,
        reviews=reviews,
    )
