"""Placement API: student delivery + CLE review.

Two routers in one module so the delivery/review boundary is visible in one
place rather than spread across files:

* ``/placement/*`` is student-facing and returns only safe fields;
* ``/placement/review/*`` is instructor-gated and is the only surface that ever
  returns a key, an answer text, a rationale or a reference band.

Every mutation checks the attempt state, is idempotent where the client may
retry, and appends an audit row in the same transaction as the change.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.models.placement import (
    PlacementAttempt,
    PlacementForm,
    PlacementItem,
    PlacementResponse,
    PlacementTestVersion,
)
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.placement import (
    AttemptDetailOut,
    AttemptEvidenceOut,
    AttemptOut,
    AttemptStartIn,
    AudioGrantOut,
    DecisionIn,
    DecisionOut,
    InterruptionIn,
    PlacementIntroOut,
    PreflightOut,
    ResponseSaveIn,
    ResponseSaveOut,
    ResultOut,
    ReviewQueueItemOut,
    ReviewQueueOut,
    VersionOut,
)
from app.services import placement as svc
from app.services import placement_bank, placement_state

router = APIRouter(prefix="/placement", tags=["placement"])
review_router = APIRouter(prefix="/placement/review", tags=["placement-review"])
admin_router = APIRouter(prefix="/placement/versions", tags=["placement-admin"])

#: Shown with every result, released or not. The learner must never be able to
#: read a Meli screen as an official HSK outcome or a final course decision.
CLAIM_LIMIT = (
    "This is an internal Meli/CLE placement screener. It is not an official HSK "
    "examination or score report, and a course is confirmed only after CLE review."
)

COMPARABILITY_NOTE = (
    "All forms cover the same skills and reference levels. They are built to the "
    "same blueprint but are not statistically equated, so results are not compared "
    "between forms."
)


def _fail(error: svc.PlacementError) -> HTTPException:
    """Map a typed service error to a status code.

    Codes are stable and machine-readable; the message is written for a learner
    and never carries an item, a key or a stack detail.
    """
    codes = {
        "NO_PUBLISHED_VERSION": status.HTTP_503_SERVICE_UNAVAILABLE,
        "WINDOW_CLOSED": status.HTTP_409_CONFLICT,
        "ATTEMPTS_EXHAUSTED": status.HTTP_409_CONFLICT,
        "NO_ELIGIBLE_FORM": status.HTTP_409_CONFLICT,
        "ATTEMPT_CONFLICT": status.HTTP_409_CONFLICT,
        "ATTEMPT_NOT_EDITABLE": status.HTTP_409_CONFLICT,
        "ATTEMPT_EXPIRED": status.HTTP_409_CONFLICT,
        "ATTEMPT_NOT_SUBMITTABLE": status.HTTP_409_CONFLICT,
        "ILLEGAL_TRANSITION": status.HTTP_409_CONFLICT,
        "RELEASE_NOT_APPROVED": status.HTTP_409_CONFLICT,
        "UNKNOWN_ITEM": status.HTTP_404_NOT_FOUND,
        "INVALID_RESPONSE": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "OVERRIDE_NEEDS_COURSE": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "REASON_REQUIRED": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "UNKNOWN_ACTION": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "BLOCKED_BY_CONTENT": status.HTTP_409_CONFLICT,
        # Audio delivery. All conflicts rather than client errors: the request
        # is well formed, the attempt's state is what refuses it.
        "AUDIO_NOT_AVAILABLE": status.HTTP_409_CONFLICT,
        "ITEM_HAS_NO_AUDIO": status.HTTP_409_CONFLICT,
        "AUDIO_PLAYS_EXHAUSTED": status.HTTP_409_CONFLICT,
    }
    return HTTPException(
        status_code=codes.get(error.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": error.code, "message": error.message},
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _seconds_remaining(attempt: PlacementAttempt) -> int | None:
    if attempt.expires_at is None or attempt.state != "in_progress":
        return None
    expires = attempt.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))


async def _load_own_attempt(
    attempt_id: uuid.UUID, user: User, db: AsyncSession
) -> PlacementAttempt:
    """Fetch an attempt the caller owns, or 404.

    404 rather than 403 on someone else's attempt: a 403 would confirm the
    attempt exists, which is itself information about another learner.
    """
    attempt = await db.get(PlacementAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ATTEMPT_NOT_FOUND", "message": "Placement attempt not found."},
        )
    return attempt


async def _attempt_out(
    db: AsyncSession, attempt: PlacementAttempt, *, form_code: str | None = None
) -> AttemptOut:
    form = await db.get(PlacementForm, attempt.form_id)
    if form_code is None:
        form_code = form.form_code if form else ""
    # The package is explicit that approved audio does not exist yet and that a
    # proctor reads each script twice until it does. An empty manifest is that
    # state, and the client needs to know so it does not offer a silent button.
    audio_available = bool((form.audio_manifest if form else None) or {})

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
    total = int(
        (
            await db.execute(
                select(func.count(PlacementItem.id)).where(
                    PlacementItem.form_id == attempt.form_id,
                    # Must match delivery_items, or the progress bar can never
                    # reach its own denominator.
                    PlacementItem.is_active.is_(True),
                )
            )
        ).scalar_one()
    )

    return AttemptOut(
        id=str(attempt.id),
        state=attempt.state,
        attempt_number=attempt.attempt_number,
        form_code=form_code,
        audio_available=audio_available,
        started_at=_iso(attempt.started_at),
        expires_at=_iso(attempt.expires_at),
        submitted_at=_iso(attempt.submitted_at),
        seconds_remaining=_seconds_remaining(attempt),
        answered_count=answered,
        total_items=total,
    )


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------


@router.get("", response_model=APIResponse[PlacementIntroOut])
async def get_intro(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Purpose, privacy, structure and attempt policy, before any timer.

    Always 200. "The test is not open" is an answer to this question, not a
    fault, so it comes back as data the closed screen renders from.
    """
    try:
        version = await svc.active_version(db)
    except svc.PlacementError:
        return APIResponse(
            success=True,
            data=PlacementIntroOut(available=False, unavailable_reason="not_published"),
        )

    if not svc._window_open(version, datetime.now(timezone.utc)):
        return APIResponse(
            success=True,
            data=PlacementIntroOut(
                available=False,
                unavailable_reason="window_closed",
                version_code=version.version_code,
                window_opens_at=_iso(version.window_opens_at),
                window_closes_at=_iso(version.window_closes_at),
            ),
        )

    # Counted on ONE form, not divided across all of them: the learner sits a
    # single form, and integer-dividing a non-uniform bank reported section
    # counts that were simply wrong.
    sample_form = (
        await db.execute(
            select(PlacementForm.id)
            .where(
                PlacementForm.test_version_id == version.id,
                PlacementForm.status == "active",
            )
            .order_by(PlacementForm.form_code)
            .limit(1)
        )
    ).scalar_one_or_none()
    counts = (
        await db.execute(
            select(PlacementItem.section, func.count(PlacementItem.id))
            .where(
                PlacementItem.form_id == sample_form,
                PlacementItem.is_active.is_(True),
            )
            .group_by(PlacementItem.section)
        )
    ).all()
    section_counts = {section: total for section, total in counts}

    prior = await svc._prior_attempts(db, user_id=user.id, version_id=version.id)
    used = sum(1 for a in prior if a.state in placement_state.CONSUMING_STATES)

    boundary = version.claim_boundary or {}
    return APIResponse(
        success=True,
        data=PlacementIntroOut(
            available=True,
            version_code=version.version_code,
            duration_minutes=version.duration_minutes,
            section_counts=section_counts,
            total_items=sum(section_counts.values()),
            max_attempts=version.max_attempts,
            attempts_used=used,
            attempts_remaining=max(0, version.max_attempts - used),
            purpose=boundary.get("purpose", CLAIM_LIMIT),
            privacy=boundary.get("privacy", ""),
            window_opens_at=_iso(version.window_opens_at),
            window_closes_at=_iso(version.window_closes_at),
            comparability_note=COMPARABILITY_NOTE,
        ),
    )


@router.post("/attempts", response_model=APIResponse[AttemptOut])
async def start_attempt(
    payload: AttemptStartIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create (or resume) an attempt and allocate a form."""
    try:
        attempt = await svc.create_attempt(
            db,
            user=user,
            declared_band=payload.declared_band,
        )
    except svc.PlacementError as error:
        raise _fail(error) from error
    await db.commit()
    await db.refresh(attempt)
    return APIResponse(success=True, data=await _attempt_out(db, attempt))


async def _advance(
    attempt_id: uuid.UUID, target: str, user: User, db: AsyncSession
) -> APIResponse[AttemptOut]:
    """Move an attempt one step, idempotently.

    Re-posting the step the attempt is CURRENTLY on returns it unchanged, so a
    client retry after a dropped response does not strand the learner. Posting a
    step the attempt has already moved past is a genuine conflict and still
    errors -- it means the client's idea of the flow is stale.
    """
    attempt = await _load_own_attempt(attempt_id, user, db)
    if attempt.state == target:
        return APIResponse(success=True, data=await _attempt_out(db, attempt))

    try:
        attempt = await svc.advance(db, attempt=attempt, target=target, actor=user)
    except placement_state.PlacementStateError as error:
        raise _fail(svc.PlacementError(error.code, error.message)) from error
    await db.commit()
    await db.refresh(attempt)
    return APIResponse(success=True, data=await _attempt_out(db, attempt))


# Three explicit paths rather than one `{step}` parameter. A catch-all segment
# here would also match `submit`, `responses` and `interruptions`, silently
# shadowing them, and route ordering is too fragile a thing to rely on.
@router.post("/attempts/{attempt_id}/confirm-eligibility", response_model=APIResponse[AttemptOut])
async def confirm_eligibility(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _advance(attempt_id, "eligibility_confirmed", user, db)


@router.post(
    "/attempts/{attempt_id}/acknowledge-instructions",
    response_model=APIResponse[AttemptOut],
)
async def acknowledge_instructions(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _advance(attempt_id, "instructions_acknowledged", user, db)


@router.post("/attempts/{attempt_id}/begin", response_model=APIResponse[AttemptOut])
async def begin_attempt(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start the controlled timer. This is the point of no return."""
    return await _advance(attempt_id, "in_progress", user, db)


@router.get("/attempts/{attempt_id}", response_model=APIResponse[AttemptDetailOut])
async def get_attempt(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The attempt plus its safe item payload and any saved answers.

    Items are released ONLY once the timer is running.

    Acknowledging the instructions is not the sitting starting: it is the screen
    before it. Delivering the paper there would let anyone calling this endpoint
    read all thirty questions untimed and then start the clock, which defeats
    the point of a timed screener. The instructions screen never needs them.
    """
    attempt = await _load_own_attempt(attempt_id, user, db)
    base = await _attempt_out(db, attempt)

    items: list[dict[str, Any]] = []
    saved: dict[str, str | None] = {}
    if attempt.state == "in_progress":
        items = await svc.delivery_items(db, attempt=attempt)
        rows = (
            (
                await db.execute(
                    select(PlacementResponse).where(
                        PlacementResponse.attempt_id == attempt.id
                    )
                )
            )
            .scalars()
            .all()
        )
        saved = {str(row.item_id): row.response for row in rows}

    return APIResponse(
        success=True,
        data=AttemptDetailOut(**base.model_dump(), items=items, saved_responses=saved),
    )


@router.put("/attempts/{attempt_id}/responses", response_model=APIResponse[ResponseSaveOut])
async def save_response(
    attempt_id: uuid.UUID,
    payload: ResponseSaveIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Autosave one answer. Safe to retry."""
    attempt = await _load_own_attempt(attempt_id, user, db)
    try:
        row = await svc.save_response(
            db,
            attempt=attempt,
            item_id=uuid.UUID(payload.item_id),
            response=payload.response,
            time_spent_ms=payload.time_spent_ms,
            audio_play_count=payload.audio_play_count,
            connection_state=payload.connection_state,
        )
    except svc.PlacementError as error:
        raise _fail(error) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UNKNOWN_ITEM", "message": "That question is not part of this attempt."},
        ) from error
    await db.commit()
    # `updated_at` is computed server-side by the column's onupdate, so
    # SQLAlchemy expires it after the flush. Reading it without this refresh
    # triggers a lazy load from inside the response construction, which an async
    # session cannot service.
    await db.refresh(row, ["updated_at"])
    return APIResponse(
        success=True,
        data=ResponseSaveOut(
            item_id=str(row.item_id),
            response=row.response,
            change_count=row.change_count,
            saved_at=_iso(row.updated_at) or "",
        ),
    )


@router.post(
    "/attempts/{attempt_id}/items/{item_id}/audio",
    response_model=APIResponse[AudioGrantOut],
)
async def play_item_audio(
    attempt_id: uuid.UUID,
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Spend one playback of a listening item and return a link to it.

    POST, not GET: this mutates the attempt. Each call consumes one of the
    item's allowed listenings, which is why the client cannot be trusted to
    count them and why the URL it gets back expires quickly.
    """
    attempt = await _load_own_attempt(attempt_id, user, db)
    try:
        url, used, allowed = await svc.issue_audio_url(db, attempt=attempt, item_id=item_id)
    except svc.PlacementError as error:
        raise _fail(error) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UNKNOWN_ITEM", "message": "That question is not part of this attempt."},
        ) from error
    await db.commit()
    return APIResponse(
        success=True,
        data=AudioGrantOut(
            url=url,
            plays_used=used,
            plays_allowed=allowed,
            expires_in_seconds=svc.AUDIO_URL_TTL_SECONDS,
        ),
    )


@router.post("/attempts/{attempt_id}/interruptions", response_model=APIResponse[AttemptOut])
async def report_interruption(
    attempt_id: uuid.UUID,
    payload: InterruptionIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a reconnect or audio failure so review can see it."""
    attempt = await _load_own_attempt(attempt_id, user, db)
    try:
        await svc.record_interruption(
            db, attempt=attempt, kind=payload.kind, detail=payload.detail
        )
    except svc.PlacementError as error:
        raise _fail(error) from error
    await db.commit()
    await db.refresh(attempt)
    return APIResponse(success=True, data=await _attempt_out(db, attempt))


@router.post("/attempts/{attempt_id}/submit", response_model=APIResponse[ResultOut])
async def submit(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit atomically, score, and return the pending-review state."""
    attempt = await _load_own_attempt(attempt_id, user, db)
    try:
        attempt = await svc.submit_attempt(db, attempt=attempt, actor=user)
    except svc.PlacementError as error:
        # No explicit rollback: `get_db`'s `async with` closes the session on the
        # way out, which discards the uncommitted transaction. Rolling back here
        # as well would additionally expire every object in the identity map,
        # which is a side effect this handler has no business causing.
        raise _fail(error) from error
    await db.commit()
    await db.refresh(attempt)
    return APIResponse(success=True, data=await _result_out(db, attempt))


async def _result_out(db: AsyncSession, attempt: PlacementAttempt) -> ResultOut:
    """The learner's view. No score, no band, no course until released."""
    course = await svc.released_course(db, attempt=attempt)
    return ResultOut(
        attempt_id=str(attempt.id),
        state=attempt.state,
        released=attempt.state in placement_state.RELEASED_STATES,
        submitted_at=_iso(attempt.submitted_at),
        recommended_course=course,
        claim_limit=CLAIM_LIMIT,
    )


@router.get("/attempts/{attempt_id}/result", response_model=APIResponse[ResultOut])
async def get_result(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _load_own_attempt(attempt_id, user, db)
    return APIResponse(success=True, data=await _result_out(db, attempt))


@router.get("/attempts", response_model=APIResponse[list[AttemptOut]])
async def list_my_attempts(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    rows = (
        (
            await db.execute(
                select(PlacementAttempt)
                .where(PlacementAttempt.user_id == user.id)
                .order_by(PlacementAttempt.attempt_number)
            )
        )
        .scalars()
        .all()
    )
    return APIResponse(
        success=True, data=[await _attempt_out(db, attempt) for attempt in rows]
    )


# ---------------------------------------------------------------------------
# CLE review (instructor-gated)
# ---------------------------------------------------------------------------


@review_router.get("/queue", response_model=APIResponse[ReviewQueueOut])
async def review_queue(
    request: Request,
    state: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    reviewer: User = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Attempts awaiting a CLE decision, most recently submitted first.

    ``expired`` is included even though there is nothing to score: the learner's
    sitting ended with no answers, which cost them an attempt, and CLE needs to
    be able to see it to invalidate it and give the attempt back.
    """
    # Everything a reviewer still has work to do on. `approved` and `overridden`
    # belong here: a decision without a release has not reached the learner, and
    # omitting them meant an approved attempt vanished from the queue and was
    # never released while the learner polled the pending screen forever.
    open_states = [
        "scored", "review_pending", "technical_review", "advising_required",
        "expired", "approved", "overridden",
    ]
    wanted = [state] if state else open_states

    total = int(
        (
            await db.execute(
                select(func.count(PlacementAttempt.id)).where(
                    PlacementAttempt.state.in_(wanted)
                )
            )
        ).scalar_one()
    )
    rows = (
        await db.execute(
            select(PlacementAttempt, PlacementForm.form_code, User.full_name, User.email)
            .join(PlacementForm, PlacementForm.id == PlacementAttempt.form_id)
            .join(User, User.id == PlacementAttempt.user_id)
            .where(PlacementAttempt.state.in_(wanted))
            # created_at breaks the tie so an expired attempt, which has no
            # submitted_at, does not sink below everything else and vanish.
            .order_by(
                PlacementAttempt.submitted_at.desc().nullslast(),
                PlacementAttempt.created_at.desc(),
            )
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()

    items = [
        ReviewQueueItemOut(
            attempt_id=str(attempt.id),
            student_name=name,
            student_email=email,
            attempt_number=attempt.attempt_number,
            form_code=form_code,
            state=attempt.state,
            confidence=attempt.confidence,
            provisional_course=attempt.provisional_course,
            highest_sustained_band=attempt.highest_sustained_band,
            review_flags=list(attempt.review_flags or []),
            submitted_at=_iso(attempt.submitted_at),
        )
        for attempt, form_code, name, email in rows
    ]

    # "Blocked" is a distinct count from "needs review": an attempt whose form
    # contains a disputed key cannot be approved at all until CLE fixes the
    # content, so grouping it with ordinary review work would hide the blocker.
    # Every row must be counted somewhere, or the header reads zero while work
    # sits in the list and nobody opens it.
    blocked = sum(
        1 for i in items
        if "item_key_disputed" in i.review_flags or "form_compromised" in i.review_flags
    )
    needs_review = sum(
        1
        for i in items
        if i.state in {"review_pending", "technical_review", "advising_required", "expired"}
    )
    ready = sum(1 for i in items if i.state in {"scored", "approved", "overridden"})

    await svc.record_audit(
        db,
        actor=reviewer,
        actor_role="instructor",
        event_type="placement.review.queue.read",
        entity_kind="placement_review_queue",
        entity_id=reviewer.id,
        request_id=request.headers.get("x-request-id"),
        metadata={"returned": len(items), "total": total, "page": page},
    )
    await db.commit()

    return APIResponse(
        success=True,
        data=ReviewQueueOut(
            needs_review=needs_review,
            ready_to_approve=ready,
            blocked=blocked,
            total=total,
            page=page,
            items=items,
        ),
    )


@review_router.get(
    "/attempts/{attempt_id}", response_model=APIResponse[AttemptEvidenceOut]
)
async def attempt_evidence(
    attempt_id: uuid.UUID,
    request: Request,
    reviewer: User = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """The full evidence bundle, including keys. Instructor-only."""
    attempt = await db.get(PlacementAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ATTEMPT_NOT_FOUND", "message": "Placement attempt not found."},
        )
    student = await db.get(User, attempt.user_id)
    evidence = await svc.build_evidence(db, attempt=attempt)
    payload = evidence.as_dict()
    digest = placement_state.evidence_snapshot_hash(payload)

    # Reading a learner's full answer sheet, keys and PII is an act worth
    # recording. Without this there is no answer to "who looked at this".
    await svc.record_audit(
        db,
        actor=reviewer,
        actor_role="instructor",
        event_type="placement.review.evidence.read",
        entity_kind="placement_attempt",
        entity_id=attempt.id,
        request_id=request.headers.get("x-request-id"),
        after_hash=digest,
    )
    await db.commit()

    return APIResponse(
        success=True,
        data=AttemptEvidenceOut(
            **{k: v for k, v in payload.items() if k != "attempt_id"},
            attempt_id=str(attempt.id),
            student_name=student.full_name if student else None,
            student_email=student.email if student else None,
            evidence_hash=digest,
        ),
    )


@review_router.post(
    "/attempts/{attempt_id}/decision", response_model=APIResponse[DecisionOut]
)
async def record_decision(
    attempt_id: uuid.UUID,
    payload: DecisionIn,
    reviewer: User = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Approve, override, request advising, invalidate, or release."""
    attempt = await db.get(PlacementAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ATTEMPT_NOT_FOUND", "message": "Placement attempt not found."},
        )

    evidence = (await svc.build_evidence(db, attempt=attempt)).as_dict()
    digest = placement_state.evidence_snapshot_hash(evidence)
    if payload.evidence_hash and payload.evidence_hash != digest:
        # The attempt changed under the reviewer (a rescore, another decision).
        # Committing now would attach their name to evidence they never saw.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EVIDENCE_STALE",
                "message": "This attempt changed since you opened it. Reload before deciding.",
            },
        )

    try:
        review = await svc.record_decision(
            db,
            attempt=attempt,
            reviewer=reviewer,
            action=payload.action,
            final_course=payload.final_course,
            reason_code=payload.reason_code,
            reason_text=payload.reason_text,
            evidence=evidence,
        )
    except svc.PlacementError as error:
        # See the note on submit(): the session's own teardown discards the
        # transaction, and an explicit rollback would expire live objects.
        raise _fail(error) from error
    await db.commit()
    await db.refresh(attempt)

    return APIResponse(
        success=True,
        data=DecisionOut(
            attempt_id=str(attempt.id),
            state=attempt.state,
            action=review.action,
            final_course=review.final_course,
        ),
    )


# ---------------------------------------------------------------------------
# Version administration
# ---------------------------------------------------------------------------


@admin_router.get("", response_model=APIResponse[list[VersionOut]])
async def list_versions(
    _: User = Depends(require_instructor), db: AsyncSession = Depends(get_db)
):
    versions = (
        (await db.execute(select(PlacementTestVersion).order_by(PlacementTestVersion.created_at)))
        .scalars()
        .all()
    )
    out: list[VersionOut] = []
    for version in versions:
        form_count = int(
            (
                await db.execute(
                    select(func.count(PlacementForm.id)).where(
                        PlacementForm.test_version_id == version.id
                    )
                )
            ).scalar_one()
        )
        out.append(
            VersionOut(
                id=str(version.id),
                version_code=version.version_code,
                status=version.status,
                scoring_rule_version=version.scoring_rule_version,
                key_version=version.key_version,
                max_attempts=version.max_attempts,
                duration_minutes=version.duration_minutes,
                window_opens_at=_iso(version.window_opens_at),
                window_closes_at=_iso(version.window_closes_at),
                published_at=_iso(version.published_at),
                form_count=form_count,
                item_count=await placement_bank.count_items(db, version.id),
            )
        )
    return APIResponse(success=True, data=out)


@admin_router.get("/{version_id}/preflight", response_model=APIResponse[PreflightOut])
async def preflight(
    version_id: uuid.UUID,
    _: User = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Everything that must be resolved before this version can go live."""
    version = await db.get(PlacementTestVersion, version_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "VERSION_NOT_FOUND", "message": "Version not found."},
        )
    result = await placement_bank.preflight_version(db, version)
    return APIResponse(
        success=True,
        data=PreflightOut(status=version.status, **result.as_dict()),
    )


@admin_router.post("/{version_id}/publish", response_model=APIResponse[VersionOut])
async def publish_version(
    version_id: uuid.UUID,
    request: Request,
    reviewer: User = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Publish a version, but only if preflight is clean.

    The gate is the point. The v1.2 package carried two items whose key the
    content owner disputed, and publishing over that would have meant scoring a
    learner on a question with no defensible answer. v1.3 revised them and now
    preflights clean, which is the gate working rather than the gate being
    unnecessary: it stays here, unchanged, for the next package.
    """
    version = await db.get(PlacementTestVersion, version_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "VERSION_NOT_FOUND", "message": "Version not found."},
        )
    if version.status == "published":
        return APIResponse(success=True, data=await _version_out(db, version))

    result = await placement_bank.preflight_version(db, version)
    if not result.can_publish:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PREFLIGHT_FAILED",
                "message": (
                    f"{len(result.blocking)} blocking issue(s) must be resolved "
                    "before this version can be published."
                ),
            },
        )

    already = (
        await db.execute(
            select(PlacementTestVersion).where(PlacementTestVersion.status == "published")
        )
    ).scalar_one_or_none()
    if already is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_ALREADY_PUBLISHED",
                "message": f"Retire '{already.version_code}' before publishing another version.",
            },
        )

    version.status = "published"
    version.published_by = reviewer.id
    version.published_at = datetime.now(timezone.utc)
    try:
        await db.flush()
    except IntegrityError as error:
        # uq_placement_versions_single_published: another publish won the race
        # between our check and our write.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_ALREADY_PUBLISHED",
                "message": "Another version was published while this request was in flight.",
            },
        ) from error
    await svc.record_audit(
        db,
        actor=reviewer,
        actor_role="instructor",
        event_type="placement.version.published",
        entity_kind="placement_test_version",
        entity_id=version.id,
        request_id=request.headers.get("x-request-id"),
        metadata={
            "version_code": version.version_code,
            "key_version": version.key_version,
            "advisory_findings": len(result.findings),
        },
    )
    await db.commit()
    await db.refresh(version)
    return APIResponse(success=True, data=await _version_out(db, version))


@admin_router.post("/{version_id}/retire", response_model=APIResponse[VersionOut])
async def retire_version(
    version_id: uuid.UUID,
    request: Request,
    reviewer: User = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    version = await db.get(PlacementTestVersion, version_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "VERSION_NOT_FOUND", "message": "Version not found."},
        )
    if version.status == "retired":
        return APIResponse(success=True, data=await _version_out(db, version))

    live = int(
        (
            await db.execute(
                select(func.count(PlacementAttempt.id)).where(
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
        ).scalar_one()
    )
    if live:
        # Retiring under a live sitting strands the learner with a running
        # clock and no way back into their own attempt.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_HAS_LIVE_ATTEMPTS",
                "message": (
                    f"{live} learner(s) are part-way through this version. "
                    "Retiring it now would strand them."
                ),
            },
        )

    version.status = "retired"
    version.retired_at = datetime.now(timezone.utc)
    await db.flush()
    await svc.record_audit(
        db,
        actor=reviewer,
        actor_role="instructor",
        event_type="placement.version.retired",
        entity_kind="placement_test_version",
        entity_id=version.id,
        request_id=request.headers.get("x-request-id"),
        metadata={"version_code": version.version_code},
    )
    await db.commit()
    await db.refresh(version)
    return APIResponse(success=True, data=await _version_out(db, version))


async def _version_out(db: AsyncSession, version: PlacementTestVersion) -> VersionOut:
    form_count = int(
        (
            await db.execute(
                select(func.count(PlacementForm.id)).where(
                    PlacementForm.test_version_id == version.id
                )
            )
        ).scalar_one()
    )
    return VersionOut(
        id=str(version.id),
        version_code=version.version_code,
        status=version.status,
        scoring_rule_version=version.scoring_rule_version,
        key_version=version.key_version,
        max_attempts=version.max_attempts,
        duration_minutes=version.duration_minutes,
        window_opens_at=_iso(version.window_opens_at),
        window_closes_at=_iso(version.window_closes_at),
        published_at=_iso(version.published_at),
        form_count=form_count,
        item_count=await placement_bank.count_items(db, version.id),
    )
