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

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
import logging

from app.services.placement_state import PlacementStateError

logger = logging.getLogger(__name__)

#: Grace beyond the published duration before the server stops accepting saves.
#: A learner whose last answer lands two seconds after the timer should not lose
#: it to clock skew; a learner still answering ten minutes later should.
SUBMIT_GRACE_SECONDS = 120

#: Ceiling on a granted extra-time accommodation, in minutes. Generous (four
#: hours on a thirty-minute paper) but finite: a stored value of 100000 would
#: otherwise put the deadline two months out, and a malformed one would raise
#: out of the request. An accommodation beyond this is a conversation, not a
#: field.
MAX_EXTRA_MINUTES = 240


def _granted_extra_minutes(
    accommodation: Mapping[str, Any] | None, duration_minutes: int
) -> int:
    """Extra minutes to add to the deadline, from a CLE-granted accommodation.

    Total, not doubled: an ``extended_time`` grant with no stated increment used
    to silently hand over a second full sitting. Unparseable and out-of-range
    values clamp rather than raising, because failing a learner's start request
    over a bad stored field would be worse than granting the default.
    """
    if not accommodation or not accommodation.get("extended_time"):
        return 0
    try:
        requested = int(accommodation.get("extra_minutes", duration_minutes))
    except (TypeError, ValueError):
        requested = duration_minutes
    return max(0, min(requested, MAX_EXTRA_MINUTES))


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

    # "How many attempts has this learner spent" and "what number is this row"
    # are DIFFERENT questions, and using one answer for both bricked learners
    # permanently. The quota is counted from consuming states; the number must
    # come from every prior row, because uq_placement_attempts_user_version_number
    # covers all of them regardless of state. An invalidated or abandoned attempt
    # is not consuming, so numbering from the quota reused a number that already
    # existed and every retry died on the unique index.
    next_number = max((a.attempt_number for a in prior), default=0) + 1

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
            # Every form the learner has actually SEEN is excluded, which is not
            # the same as every form that consumed an attempt. Invalidating an
            # attempt gives the learner their allowance back; it does not
            # un-read the paper, so re-serving that form would turn a retake
            # into a memory test. Only an attempt that never started the timer
            # (abandoned) leaves its form available, because the paper is
            # released only at `in_progress`.
            used_form_codes=[
                _form_code(forms, attempt.form_id)
                for attempt in prior
                if attempt.state != "abandoned"
            ],
            attempt_number=next_number,
        )
    except placement_state.FormRotationError as error:
        raise PlacementError(error.code, error.message) from error

    form = next(f for f in forms if f.form_code == allocation.form_code)

    attempt = PlacementAttempt(
        user_id=user.id,
        test_version_id=version.id,
        form_id=form.id,
        attempt_number=next_number,
        state="created",
        allocation_reference=allocation.reference,
        declared_band=declared_band,
        accommodation=dict(accommodation) if accommodation else None,
    )
    db.add(attempt)
    # Captured BEFORE the rollback below: rollback expires every instance in the
    # identity map, including primary keys, so reading `user.id` afterwards is a
    # lazy refresh on an async session and raises MissingGreenlet -- turning the
    # recovery path into an uncaught 500.
    user_id, version_id = user.id, version.id
    try:
        await db.flush()
    except IntegrityError as error:
        # The only race this can legitimately be is the single-open partial
        # index: another request created the learner's attempt first, so resume
        # it. Any other constraint is a real bug and must not be disguised as a
        # lost race.
        await db.rollback()
        resumed = (
            await db.execute(
                select(PlacementAttempt).where(
                    PlacementAttempt.user_id == user_id,
                    PlacementAttempt.test_version_id == version_id,
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
        extra = _granted_extra_minutes(attempt.accommodation, minutes)
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
        # Upsert, not INSERT. The client fires autosaves without awaiting the
        # previous one, so two writes for the same item can both find no row;
        # a plain INSERT then raises IntegrityError and 500s mid-exam. On
        # conflict the other write already landed, so re-read it and fall
        # through to the update path below.
        stmt = (
            pg_insert(PlacementResponse)
            .values(
                id=uuid.uuid4(),
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
            .on_conflict_do_nothing(index_elements=["attempt_id", "item_id"])
            .returning(PlacementResponse.id)
        )
        inserted = (await db.execute(stmt)).scalar_one_or_none()
        if inserted is not None:
            await db.flush()
            return await db.get(PlacementResponse, inserted)
        existing = (
            await db.execute(
                select(PlacementResponse).where(
                    PlacementResponse.attempt_id == attempt.id,
                    PlacementResponse.item_id == item.id,
                )
            )
        ).scalar_one()

    if existing.response != value:
        # Filling a blank is not a change of mind. A row can already exist with
        # no answer for reasons that have nothing to do with the learner
        # revising: playing an item's audio claims a playback and creates the
        # row, and a partially-built ordering answer is saved as NULL so paging
        # away does not discard it. Counting None -> "B" as a change would put
        # a revision on a reviewer's screen for every listening item the
        # learner simply answered once, which is exactly the false signal the
        # idempotency rule above exists to prevent.
        if existing.response is not None:
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


#: How long an issued audio link stays usable. Long enough to survive a slow
#: network and a learner who presses play a moment later, short enough that a
#: link copied out of devtools is worthless by the time it is shared.
AUDIO_URL_TTL_SECONDS = 300


async def issue_audio_url(
    db: AsyncSession,
    *,
    attempt: PlacementAttempt,
    item_id: uuid.UUID,
) -> tuple[str, int, int]:
    """Spend one playback and hand back a short-lived link.

    The play allowance is enforced here rather than in the client, because the
    client cannot enforce it. ``audio_playback`` is a property of the exam (the
    paper says a script is heard once or twice), so a learner who refetches the
    URL, reloads the page or replays the element must not get a third listening
    that the item's difficulty was never calibrated for.

    Counting on *issue* rather than on playback completion is deliberate: a
    learner who starts a clip and navigates away has heard it, and the opposite
    choice would let anyone farm unlimited plays by aborting each one.

    Returns ``(url, plays_used, plays_allowed)``.
    """
    if attempt.state not in placement_state.MUTABLE_STATES:
        raise PlacementError("ATTEMPT_NOT_EDITABLE", "this attempt can no longer be changed")

    expires = _aware(attempt.expires_at)
    if expires is not None and _now() > expires + timedelta(seconds=SUBMIT_GRACE_SECONDS):
        raise PlacementError("ATTEMPT_EXPIRED", "the time limit for this attempt has passed")

    item = await db.get(PlacementItem, item_id)
    if item is None or item.form_id != attempt.form_id:
        raise ValueError("item is not part of this attempt")

    allowed = item.audio_playback or 0
    if allowed <= 0:
        raise PlacementError("ITEM_HAS_NO_AUDIO", "this question has no audio")

    form = await db.get(PlacementForm, attempt.form_id)
    manifest = (form.audio_manifest if form else None) or {}
    entry = manifest.get(str(item.question_number))
    if not entry:
        raise PlacementError(
            "AUDIO_NOT_AVAILABLE", "no recording has been published for this question"
        )
    key = entry.get("r2_key") if isinstance(entry, dict) else entry

    # Claim the play before minting the link. A conditional UPDATE makes two
    # concurrent presses race for the same row rather than both winning, which
    # a read-then-write would allow.
    row = (
        await db.execute(
            select(PlacementResponse).where(
                PlacementResponse.attempt_id == attempt.id,
                PlacementResponse.item_id == item.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = await save_response(db, attempt=attempt, item_id=item.id, response=None)

    claimed = (
        await db.execute(
            update(PlacementResponse)
            .where(
                PlacementResponse.id == row.id,
                PlacementResponse.audio_play_count < allowed,
            )
            .values(audio_play_count=PlacementResponse.audio_play_count + 1)
            .returning(PlacementResponse.audio_play_count)
        )
    ).scalar_one_or_none()
    if claimed is None:
        raise PlacementError(
            "AUDIO_PLAYS_EXHAUSTED",
            f"this question may be heard {allowed} time(s), and all have been used",
        )

    from app.services.storage import generate_presigned_url

    url = generate_presigned_url(key, expiration=AUDIO_URL_TTL_SECONDS)
    await db.flush()
    return url, int(claimed), allowed


#: Interruptions a learner may report, per attempt. Generous for a real bad
#: connection, finite because the array is learner-controlled and is inside the
#: evidence bundle a reviewer's decision is hashed against.
MAX_INTERRUPTIONS = 50


async def record_interruption(
    db: AsyncSession,
    *,
    attempt: PlacementAttempt,
    kind: str,
    detail: str | None = None,
    system: bool = False,
) -> None:
    """Append a technical event. Feeds the technical review trigger.

    Learner-reported events are only accepted while the attempt is running.
    Without that, a learner could append to a submitted attempt at will: every
    append changes the evidence hash, so each one would 409 the reviewer's
    decision as stale and they could block any decision on their own result
    indefinitely.
    """
    if not system and attempt.state != "in_progress":
        raise PlacementError(
            "ATTEMPT_NOT_EDITABLE",
            "this attempt can no longer be changed",
        )

    events = list(attempt.interruptions or [])
    if len(events) >= MAX_INTERRUPTIONS:
        # Silently capped rather than erroring: the learner is already having a
        # bad time, and the reviewer has more than enough evidence by now.
        return
    events.append({"kind": kind, "detail": detail, "at": _now().isoformat()})
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
    db: AsyncSession, *, attempt: PlacementAttempt, actor: User | None
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
            .where(
                PlacementItem.form_id == attempt.form_id,
                PlacementItem.is_active.is_(True),
            )
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
    attempt.scorable_count = result.scorable_count
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
# Expiry sweep
# ---------------------------------------------------------------------------

#: A pre-timer attempt older than this is treated as walked away from. It has
#: seen no questions (the paper is released only once the clock starts), so
#: closing it costs the learner nothing.
ABANDON_AFTER_HOURS = 24


async def sweep_stale_attempts(db: AsyncSession) -> dict[str, int]:
    """Close attempts the learner never finished. Returns per-outcome counts.

    Without this, an attempt whose learner shut their laptop stays
    ``in_progress`` forever: the partial unique index then blocks them from ever
    starting another, and CLE never sees the work they did do.

    Three outcomes, because "the timer ran out" is not one situation:

    * something went wrong (interruptions were recorded) -> ``technical_review``,
      so a human looks before any number is attached to the learner;
    * they were working and ran out of time -> submit and score it. Their
      answers are evidence, and the duration and completeness triggers will tell
      the reviewer exactly what happened. Voiding real work would be worse for
      the learner than a flagged result;
    * they never answered anything -> ``expired``. There is nothing to score,
      and inventing a band-0 result from an empty paper would be a fiction.
    """
    now = _now()
    counts = {"technical_review": 0, "submitted": 0, "expired": 0, "abandoned": 0}

    running = (
        (
            await db.execute(
                select(PlacementAttempt).where(
                    PlacementAttempt.state == "in_progress",
                    PlacementAttempt.expires_at.isnot(None),
                    PlacementAttempt.expires_at
                    < now - timedelta(seconds=SUBMIT_GRACE_SECONDS),
                )
            )
        )
        .scalars()
        .all()
    )

    for attempt in running:
      try:
        answered = int(
            (
                await db.execute(
                    select(func.count(PlacementResponse.id)).where(
                        PlacementResponse.attempt_id == attempt.id,
                        PlacementResponse.response.isnot(None),
                    )
                )
            ).scalar_one()
        )
        await record_interruption(
            db, attempt=attempt, kind="timer_expired",
            detail=f"{answered} answered when the time limit passed",
            system=True,
        )

        if attempt.interruptions and len(attempt.interruptions) > 1:
            attempt.state = "technical_review"
            counts["technical_review"] += 1
            await _audit_sweep(db, attempt, "technical_review", answered)
            continue

        if answered == 0:
            attempt.state = "expired"
            counts["expired"] += 1
            await _audit_sweep(db, attempt, "expired", answered)
            continue

        # Close it the way the learner would have, so the normal scoring and
        # review path runs and CLE sees a comparable record.
        started = _aware(attempt.started_at)
        expires = _aware(attempt.expires_at)
        attempt.state = "submitted"
        attempt.submitted_at = expires
        if started and expires:
            attempt.duration_seconds = int((expires - started).total_seconds())
        await db.flush()
        await score_attempt(db, attempt=attempt, actor=None)
        counts["submitted"] += 1
        await _audit_sweep(db, attempt, "auto_submitted", answered)
      except Exception:  # noqa: BLE001
        # One learner's bad row must not void the sweep for everyone else. The
        # cron retries in five minutes; a permanently bad row shows up in the
        # log rather than silently blocking every other expiry.
        logger.exception("placement sweep failed for attempt %s", attempt.id)

    stale_before = now - timedelta(hours=ABANDON_AFTER_HOURS)
    waiting = (
        (
            await db.execute(
                select(PlacementAttempt).where(
                    PlacementAttempt.state.in_(
                        [
                            "created",
                            "eligibility_confirmed",
                            "instructions_acknowledged",
                        ]
                    ),
                    PlacementAttempt.created_at < stale_before,
                )
            )
        )
        .scalars()
        .all()
    )
    for attempt in waiting:
        attempt.state = "abandoned"
        counts["abandoned"] += 1
        await _audit_sweep(db, attempt, "abandoned", 0)

    await db.flush()
    return counts


async def _audit_sweep(
    db: AsyncSession, attempt: PlacementAttempt, outcome: str, answered: int
) -> None:
    await record_audit(
        db,
        actor=None,
        actor_role="system",
        event_type=f"placement.attempt.swept.{outcome}",
        entity_kind="placement_attempt",
        entity_id=attempt.id,
        metadata={"answered": answered, "state": attempt.state},
    )


# ---------------------------------------------------------------------------
# CLE review
# ---------------------------------------------------------------------------


#: Flags that make an attempt unapprovable until the underlying content or
#: form is fixed. Mirrored in the client, but enforced here.
BLOCKING_FLAGS: frozenset[str] = frozenset({"item_key_disputed", "form_compromised"})

ACTION_TO_STATE = {
    "approve": "approved",
    "override": "overridden",
    "request_advising": "advising_required",
    "invalidate": "invalidated",
    # Without this, `technical_review` was a trap: the transition table allowed
    # an exit but no action mapped to one, so the only legal decision was
    # `invalidate` -- on exactly the attempts where something went wrong through
    # no fault of the learner.
    "resume_review": "review_pending",
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

    # Blocking flags were enforced only by a disabled button in the browser, so
    # a direct POST could approve an attempt whose score silently excluded an
    # item nobody can key -- and a later release would hand the learner a course
    # derived from it. The rule belongs on the server.
    if action in {"approve", "override", "release"}:
        blocking = [
            flag for flag in (attempt.review_flags or []) if flag in BLOCKING_FLAGS
        ]
        if blocking:
            raise PlacementError(
                "BLOCKED_BY_CONTENT",
                "this attempt cannot be approved while its form has an "
                "unresolved content problem; resolve the item or invalidate "
                "the attempt",
            )

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
            "scorable_count": self.attempt.scorable_count,
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
                PlacementItemKey.teacher_review,
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
            # Severity is resolved here rather than in the UI: v1.3 carries 22
            # advisory flags, and a reviewer who sees them styled like an
            # unscoreable item learns to ignore the badge that matters.
            "teacher_flags": placement_bank.annotate_flags(row.teacher_flags),
            # Why this item is in front of a reviewer, in the content owner's
            # own terms. Restricted, and this route is instructor-gated.
            "teacher_review": row.teacher_review,
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
