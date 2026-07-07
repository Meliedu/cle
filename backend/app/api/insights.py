"""Pure-read insights surface (P6 §5).

This router RESHAPES existing evidence rows — it performs NO new mastery math,
no note drafting, no alert evaluation (Decision 1, "no parallel evidence path").
Every number it returns traces to a row another system already wrote.

The student learning profile groups the caller's ``concept_mastery`` rows using
the SAME thresholds ``app/api/mastery.py::cohort_mastery`` applies — it never
recomputes them.
"""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import get_current_user, get_db, get_owned_course
from app.models import (
    Concept,
    ConceptMastery,
    ConceptTag,
    FollowUpAction,
    InstructorAlert,
    LearningEvent,
    LearningNote,
    LearningObjective,
    OutcomeCheck,
)
from app.models.course import Course
from app.models.user import User
from app.pilot import get_pilot_profile
from app.schemas.common import APIResponse
from app.schemas.insights import (
    AlertSeverityCounts,
    CohortIloMapEntry,
    CohortIloMapResponse,
    CohortMasterySummary,
    ConceptMasteryEntry,
    CourseInsightsResponse,
    EffectivenessActionGroup,
    EffectivenessResponse,
    EvidenceSource,
    IloMapEntry,
    IloMapResponse,
    LearningProfileGroups,
    LearningProfileResponse,
    ReviewQueueDepth,
    SignalDetail,
    SkillMapEntry,
    SkillMapResponse,
)

router = APIRouter(tags=["insights"])

# LearningNote.review_status values that mean an instructor has reviewed the
# note, so its AI-drafted content may be shown to the student (Core §0.2 /
# Decision 6). Mirrors ``app/api/review.py::_REVIEWED_NOTE_STATUSES`` exactly.
# The complement ('draft','queued') is AI-drafted and never surfaced to the
# student; 'archived' is a removed note and 404s for the student.
_REVIEWED_NOTE_STATUSES = frozenset({"reviewed", "edited", "merged", "split"})

# Thresholds mirror ``app/api/mastery.py::cohort_mastery`` EXACTLY — do NOT
# invent new cut points here. A mastery row only counts as evidence once its
# ``confidence >= 0.5``; a counted row is "weak" below 0.5 mastery and "strong"
# at/above it. Rows that have not yet cleared the confidence gate are surfaced
# as "developing" (still accumulating evidence) rather than fabricating a
# strong/weak verdict on thin data.
_MIN_CONFIDENCE = Decimal("0.5")
_WEAK_MASTERY_THRESHOLD = Decimal("0.5")


@router.get(
    "/users/me/courses/{course_id}/insights",
    response_model=APIResponse[LearningProfileResponse],
)
async def my_learning_profile(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[LearningProfileResponse]:
    """The caller's learning profile, reshaped from ``concept_mastery`` (pure read).

    Enrollment-scoped (``verify_enrollment`` — active enrollment only, 403
    otherwise) and limited to the caller's own ``user_id`` rows. A student with
    no confident evidence gets an empty profile with ``has_evidence=false``
    (Decision 6) — the endpoint never fabricates a score.
    """
    await verify_enrollment(db, course_id, user.id)

    rows = (
        await db.execute(
            select(ConceptMastery, Concept.name)
            .join(Concept, Concept.id == ConceptMastery.concept_id)
            .where(
                ConceptMastery.user_id == user.id,
                ConceptMastery.course_id == course_id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .order_by(Concept.name)
        )
    ).all()

    strong: list[ConceptMasteryEntry] = []
    developing: list[ConceptMasteryEntry] = []
    weak: list[ConceptMasteryEntry] = []
    has_evidence = False
    for m, name in rows:
        entry = ConceptMasteryEntry(
            concept_id=m.concept_id,
            concept_name=name,
            mastery_score=m.mastery_score,
            confidence=m.confidence,
            attempt_count=m.attempt_count,
            last_attempt_at=m.last_attempt_at,
        )
        if m.confidence < _MIN_CONFIDENCE:
            developing.append(entry)
        else:
            has_evidence = True
            if m.mastery_score < _WEAK_MASTERY_THRESHOLD:
                weak.append(entry)
            else:
                strong.append(entry)

    profile = LearningProfileResponse(
        course_id=course_id,
        has_evidence=has_evidence,
        concept_count=len(rows),
        groups=LearningProfileGroups(
            strong=strong, developing=developing, weak=weak
        ),
        disclaimer=get_pilot_profile().claim_limits["learning_profile"],
    )
    return APIResponse(success=True, data=profile)


async def _objectives_with_concept_ids(
    db: AsyncSession, course_id: uuid.UUID
) -> list[tuple[LearningObjective, list[uuid.UUID]]]:
    """Shared aggregation seam: each course objective → its tagged concept ids.

    An objective's concepts are the LIVE (non-deleted, non-merged) ``concepts``
    linked via ``concept_tags`` with ``target_kind='objective'`` and
    ``target_id = objective.id``. Pure read — the caller decides whose mastery to
    aggregate (own rows for the student view, the cohort for the teacher view).
    """
    objectives = (
        (
            await db.execute(
                select(LearningObjective)
                .where(
                    LearningObjective.course_id == course_id,
                    LearningObjective.deleted_at.is_(None),
                )
                .order_by(
                    LearningObjective.order_index, LearningObjective.statement
                )
            )
        )
        .scalars()
        .all()
    )

    tag_rows = (
        await db.execute(
            select(ConceptTag.target_id, ConceptTag.concept_id)
            .join(Concept, Concept.id == ConceptTag.concept_id)
            .where(
                ConceptTag.target_kind == "objective",
                Concept.course_id == course_id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
        )
    ).all()

    concepts_by_objective: dict[uuid.UUID, list[uuid.UUID]] = {}
    for target_id, concept_id in tag_rows:
        concepts_by_objective.setdefault(target_id, []).append(concept_id)

    return [(o, concepts_by_objective.get(o.id, [])) for o in objectives]


@router.get(
    "/users/me/courses/{course_id}/ilo-map",
    response_model=APIResponse[IloMapResponse],
)
async def my_ilo_map(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[IloMapResponse]:
    """The caller's ILO strength map, reshaped from ``concept_mastery`` (pure read).

    One row per course ``learning_objective``; strength is the mean of the
    caller's ``mastery_score`` over the concepts tagged to that objective
    (``concept_tags`` ``target_kind='objective'``). Enrollment-scoped
    (``verify_enrollment`` — active only) and limited to the caller's own rows.
    Objectives with no tagged concept that has caller evidence render
    ``has_evidence=false``, NEVER a fabricated 0 (Decision 7).
    """
    await verify_enrollment(db, course_id, user.id)

    objectives = await _objectives_with_concept_ids(db, course_id)

    mastery_rows = (
        await db.execute(
            select(ConceptMastery.concept_id, ConceptMastery.mastery_score).where(
                ConceptMastery.user_id == user.id,
                ConceptMastery.course_id == course_id,
            )
        )
    ).all()
    mastery_by_concept = {cid: score for cid, score in mastery_rows}

    entries: list[IloMapEntry] = []
    any_evidence = False
    for objective, concept_ids in objectives:
        scores = [
            mastery_by_concept[cid]
            for cid in concept_ids
            if cid in mastery_by_concept
        ]
        has_evidence = bool(scores)
        if has_evidence:
            any_evidence = True
        entries.append(
            IloMapEntry(
                objective_id=objective.id,
                statement=objective.statement,
                bloom_level=objective.bloom_level,
                has_evidence=has_evidence,
                strength=(
                    float(sum(scores) / len(scores)) if has_evidence else None
                ),
                concept_count=len(concept_ids),
                evidence_concept_count=len(scores),
            )
        )

    return APIResponse(
        success=True,
        data=IloMapResponse(
            course_id=course_id, has_evidence=any_evidence, objectives=entries
        ),
    )


@router.get(
    "/courses/{course_id}/ilo-map",
    response_model=APIResponse[CohortIloMapResponse],
)
async def cohort_ilo_map(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[CohortIloMapResponse]:
    """The cohort ILO strength map for an owned course (instructor-only, pure read).

    One row per ``learning_objective``: ``avg_strength`` is the row-level mean
    ``mastery_score`` over every student's mastery on the objective's tagged
    concepts (mirrors ``cohort_mastery``'s ``func.avg``); ``weak_students`` reuses
    the ``cohort_mastery`` weak definition (mastery < 0.5 among confidence >= 0.5),
    counted as DISTINCT weak students. ``get_owned_course`` 404s a non-owner.
    Objectives with no cohort evidence render ``has_evidence=false``, never a 0.
    """
    objectives = await _objectives_with_concept_ids(db, course.id)

    mastery_rows = (
        await db.execute(
            select(
                ConceptMastery.concept_id,
                ConceptMastery.user_id,
                ConceptMastery.mastery_score,
                ConceptMastery.confidence,
            ).where(ConceptMastery.course_id == course.id)
        )
    ).all()

    rows_by_concept: dict[uuid.UUID, list[tuple]] = {}
    for cid, uid, score, confidence in mastery_rows:
        rows_by_concept.setdefault(cid, []).append((uid, score, confidence))

    entries: list[CohortIloMapEntry] = []
    any_evidence = False
    for objective, concept_ids in objectives:
        scores: list = []
        weak_users: set[uuid.UUID] = set()
        evidence_users: set[uuid.UUID] = set()
        for cid in concept_ids:
            for uid, score, confidence in rows_by_concept.get(cid, []):
                scores.append(score)
                evidence_users.add(uid)
                if (
                    score < _WEAK_MASTERY_THRESHOLD
                    and confidence >= _MIN_CONFIDENCE
                ):
                    weak_users.add(uid)
        has_evidence = bool(scores)
        if has_evidence:
            any_evidence = True
        entries.append(
            CohortIloMapEntry(
                objective_id=objective.id,
                statement=objective.statement,
                bloom_level=objective.bloom_level,
                has_evidence=has_evidence,
                avg_strength=(
                    float(sum(scores) / len(scores)) if has_evidence else None
                ),
                weak_students=len(weak_users),
                students_with_evidence=len(evidence_users),
                concept_count=len(concept_ids),
            )
        )

    return APIResponse(
        success=True,
        data=CohortIloMapResponse(
            course_id=course.id, has_evidence=any_evidence, objectives=entries
        ),
    )


@router.get(
    "/users/me/courses/{course_id}/skill-map",
    response_model=APIResponse[SkillMapResponse],
)
async def my_skill_map(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[SkillMapResponse]:
    """The caller's skill-pattern map — HONEST, config-driven (pure read, B6).

    One entry per pilot ``skill_taxonomy`` skill. Decision 5: NO ``skill`` link
    exists anywhere in the schema — ``concept_tags.target_kind`` has
    ``objective``/``checkpoint_card``/… but NOT ``skill``, and no evidence row
    (``concept_mastery``, ``learning_notes``, …) carries a skill dimension. So
    every cell honestly renders the no-evidence state: ``has_evidence=False``
    with ``strength`` and ``sample_size`` both ``None``. This endpoint NEVER
    fabricates a score — it only exposes the config taxonomy so the frontend can
    render the "we don't have skill-level evidence yet" state.

    SEAM TO EXTEND: when a future concept→skill mapping lands (e.g. a ``skill``
    ``target_kind`` on ``concept_tags``, or a skill column on the evidence rows),
    aggregate the caller's ``concept_mastery`` over that mapping HERE and
    populate ``strength``/``sample_size`` + flip ``has_evidence`` — only where
    real evidence exists. Until then, honesty over a fabricated grid.

    Enrollment-scoped (``verify_enrollment`` — active enrollment only, 403
    otherwise) so it matches the rest of the student insights surface.
    """
    await verify_enrollment(db, course_id, user.id)

    taxonomy = get_pilot_profile().skill_taxonomy
    skills = [
        SkillMapEntry(
            skill=skill,
            label=skill.replace("_", " ").capitalize(),
            # Decision 5: no schema link exists — every cell is no-evidence.
            has_evidence=False,
            strength=None,
            sample_size=None,
        )
        for skill in taxonomy
    ]

    return APIResponse(
        success=True,
        data=SkillMapResponse(
            course_id=course_id, has_evidence=False, skills=skills
        ),
    )


# ---------------------------------------------------------------------------
# Signal detail + evidence source (B7) — id-first, dual-role, re-guarded reads.
# ---------------------------------------------------------------------------
_SIGNAL_NOT_FOUND = "Signal not found"
_EVIDENCE_NOT_FOUND = "Evidence not found"


async def _owned_course_or_404(
    db: AsyncSession, course_id: uuid.UUID, instructor: User, detail: str
) -> Course:
    """Re-derive + guard an instructor's ownership of a resolved row's course.

    The id of the resolved row is NEVER trusted (Decision 8): we re-fetch its
    course and require the acting instructor to own it. A missing / soft-deleted
    / non-owned course is a 404 so existence is never leaked.
    """
    course = await db.get(Course, course_id)
    if (
        course is None
        or course.deleted_at is not None
        or course.instructor_id != instructor.id
    ):
        raise HTTPException(status_code=404, detail=detail)
    return course


@router.get(
    "/signals/{signal_id}",
    response_model=APIResponse[SignalDetail],
)
async def get_signal(
    signal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[SignalDetail]:
    """One ``learning_note`` reshaped as a signal detail (dual-role, pure read).

    Id-first + re-guarded (Decision 8): resolve the note, RE-DERIVE its
    ``course_id``, and re-apply the owner/enrollment guard — a mismatch is a 404
    with no existence leak.

    - **Student**: sees ONLY their OWN (``user_id`` == caller) signal. Another
      student's note, a cohort note (``user_id IS NULL``) and an ``archived``
      (removed) note are all 404. A still-``draft``/``queued`` own note collapses
      to the designed waiting shape (``waiting_for_review=True``, NO AI content —
      Core §0.2). A ``reviewed`` own note carries its content.
    - **Instructor**: sees ANY signal in an OWNED course, including cohort and
      still-draft notes, always with content (they are the reviewer). Non-owner
      → 404.
    """
    note = await db.get(LearningNote, signal_id)
    if note is None:
        raise HTTPException(status_code=404, detail=_SIGNAL_NOT_FOUND)

    if user.role == "instructor":
        await _owned_course_or_404(db, note.course_id, user, _SIGNAL_NOT_FOUND)
        # The reviewer sees content regardless of review_status; never "waiting".
        reveal = True
        waiting = False
    else:
        # Student: the note must be their OWN (cohort user_id IS NULL never
        # matches) — 404 masks any other row's existence.
        if note.user_id != user.id:
            raise HTTPException(status_code=404, detail=_SIGNAL_NOT_FOUND)
        # Defense-in-depth: an active enrollment is still required (a dropped
        # student cannot pull their old signals). 403 only ever fires for the
        # caller's OWN notes, so it leaks nothing about other rows.
        await verify_enrollment(db, note.course_id, user.id)
        # 'archived' is a removed note — withheld from the student entirely.
        if note.review_status == "archived":
            raise HTTPException(status_code=404, detail=_SIGNAL_NOT_FOUND)
        reveal = note.review_status in _REVIEWED_NOTE_STATUSES
        waiting = not reveal

    detail = SignalDetail(
        id=note.id,
        course_id=note.course_id,
        user_id=note.user_id,
        review_status=note.review_status,
        waiting_for_review=waiting,
        created_at=note.created_at,
        updated_at=note.updated_at,
        # AI content only when revealed (reviewed, or the owning instructor).
        evidence_category=note.evidence_category if reveal else None,
        observed_signal=note.observed_signal if reveal else None,
        draft_interpretation=note.draft_interpretation if reveal else None,
        limitation_note=note.limitation_note if reveal else None,
        context_anchor=note.context_anchor if reveal else None,
        outcome_status=note.outcome_status if reveal else None,
        source_event_ids=list(note.source_event_ids or []) if reveal else [],
    )
    return APIResponse(success=True, data=detail)


async def _anchor_for_event(
    db: AsyncSession, event_id: uuid.UUID, *, reviewed_only: bool
) -> dict | None:
    """Best-effort ``context_anchor`` from a note that cites this event.

    A ``learning_event`` carries no anchor of its own; the "where did this come
    from" context lives on the ``learning_note`` that cites the event via its
    ``source_event_ids`` JSONB array (stored as string ids). For a student we
    restrict to REVIEWED notes so an unreviewed draft's anchor never leaks
    (Core §0.2); for an instructor any citing note qualifies. Returns ``None``
    when no qualifying note cites the event.
    """
    stmt = (
        select(LearningNote.context_anchor)
        .where(LearningNote.source_event_ids.contains([str(event_id)]))
        .order_by(LearningNote.created_at)
    )
    if reviewed_only:
        stmt = stmt.where(
            LearningNote.review_status.in_(_REVIEWED_NOTE_STATUSES)
        )
    return (await db.execute(stmt)).scalars().first()


@router.get(
    "/evidence/{event_id}/source",
    response_model=APIResponse[EvidenceSource],
)
async def get_evidence_source(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[EvidenceSource]:
    """One ``learning_event`` reshaped as its source view (dual-role, pure read).

    The "where did this come from" panel: the raw source signal
    (``source_kind`` / ``source_id`` / ``stage`` / ``event_type`` / ``value`` /
    ``occurred_at``) plus the ``context_anchor`` a reviewed note attached to it.

    Id-first + re-guarded (Decision 8): resolve the event, RE-DERIVE its
    ``course_id`` / ``user_id``, and re-apply the SAME owner/enrollment guard as
    the signal view — a student sees ONLY their own event (404 otherwise, active
    enrollment required); an instructor sees any event in an owned course (404
    for a non-owner). The event id is never trusted to imply access.
    """
    event = await db.get(LearningEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=_EVIDENCE_NOT_FOUND)

    if user.role == "instructor":
        await _owned_course_or_404(
            db, event.course_id, user, _EVIDENCE_NOT_FOUND
        )
        reviewed_only = False
    else:
        if event.user_id != user.id:
            raise HTTPException(status_code=404, detail=_EVIDENCE_NOT_FOUND)
        await verify_enrollment(db, event.course_id, user.id)
        reviewed_only = True

    context_anchor = await _anchor_for_event(
        db, event.id, reviewed_only=reviewed_only
    )

    source = EvidenceSource(
        event_id=event.id,
        course_id=event.course_id,
        user_id=event.user_id,
        source_kind=event.source_kind,
        source_id=event.source_id,
        stage=event.stage,
        event_type=event.event_type,
        value=event.value,
        occurred_at=event.occurred_at,
        context_anchor=context_anchor,
    )
    return APIResponse(success=True, data=source)


# ---------------------------------------------------------------------------
# Teacher course insights + effectiveness tracker (B8) — reshape only, owned.
# ---------------------------------------------------------------------------
# Mirrors ``learning_notes.review_status`` values that mean "AI-drafted, not yet
# instructor-reviewed" — the review-queue depth (Decision 1 / spec §5).
_PENDING_NOTE_STATUSES = ("draft", "queued")

# The full ``outcome_checks.status`` CHECK enum (``models/evidence.py``). The
# effectiveness tracker always returns every bucket, zeroed where absent, so the
# frontend can render a stable grid without inventing keys.
_OUTCOME_STATUSES = (
    "pending",
    "completed",
    "improved",
    "persistent",
    "resolved",
    "needs_review",
    "carried_forward",
)


async def _cohort_mastery_summary(
    db: AsyncSession, course_id: uuid.UUID
) -> CohortMasterySummary:
    """Reduce the ``cohort_mastery`` per-concept shape to a course summary (pure read).

    Runs the SAME per-concept aggregation as ``api/mastery.py::cohort_mastery``
    (avg mastery + the weak count where mastery < 0.5 among confidence >= 0.5),
    then collapses it: ``avg_mastery`` is the mean of each evidenced concept's
    cohort average (``None`` when no concept has evidence — never a fabricated 0),
    ``weak_student_signals`` sums the per-concept weak counts. Recomputes nothing.
    """
    rows = (
        await db.execute(
            select(
                Concept.id,
                func.avg(ConceptMastery.mastery_score).label("avg_mastery"),
                func.count()
                .filter(
                    (ConceptMastery.mastery_score < _WEAK_MASTERY_THRESHOLD)
                    & (ConceptMastery.confidence >= _MIN_CONFIDENCE)
                )
                .label("weak_students"),
                func.count(ConceptMastery.user_id).label("total"),
            )
            .select_from(Concept)
            .outerjoin(ConceptMastery, ConceptMastery.concept_id == Concept.id)
            .where(
                Concept.course_id == course_id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .group_by(Concept.id)
        )
    ).all()

    evidenced = [
        float(r.avg_mastery)
        for r in rows
        if (r.total or 0) > 0 and r.avg_mastery is not None
    ]
    return CohortMasterySummary(
        concept_count=len(rows),
        concepts_with_evidence=sum(1 for r in rows if (r.total or 0) > 0),
        avg_mastery=(sum(evidenced) / len(evidenced)) if evidenced else None,
        weak_student_signals=sum((r.weak_students or 0) for r in rows),
    )


@router.get(
    "/courses/{course_id}/insights",
    response_model=APIResponse[CourseInsightsResponse],
)
async def course_insights(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[CourseInsightsResponse]:
    """The teacher course-insights payload for an owned course (B8, pure read).

    A single RESHAPE of existing rows — NO recompute (Decision 1): the cohort
    mastery summary (``cohort_mastery`` shape), open ``instructor_alerts`` counts
    by severity (these EQUAL ``GET /courses/{id}/alerts?status=open``), and
    review-queue depth (open alerts + ``draft``/``queued`` notes).
    ``get_owned_course`` 404s a non-owner; a course with no evidence returns the
    designed empty payload (``has_evidence=false``).
    """
    cohort = await _cohort_mastery_summary(db, course.id)

    alert_rows = (
        await db.execute(
            select(InstructorAlert.severity, func.count())
            .where(
                InstructorAlert.course_id == course.id,
                InstructorAlert.status == "open",
            )
            .group_by(InstructorAlert.severity)
        )
    ).all()
    counts = AlertSeverityCounts()
    for severity, n in alert_rows:
        setattr(counts, severity, n)
    counts.total = counts.info + counts.warning + counts.critical

    pending_notes = (
        await db.execute(
            select(func.count())
            .select_from(LearningNote)
            .where(
                LearningNote.course_id == course.id,
                LearningNote.review_status.in_(_PENDING_NOTE_STATUSES),
            )
        )
    ).scalar_one()

    review_queue = ReviewQueueDepth(
        open_alerts=counts.total,
        pending_notes=pending_notes,
        total=counts.total + pending_notes,
    )

    has_evidence = (
        cohort.concepts_with_evidence > 0
        or counts.total > 0
        or pending_notes > 0
    )

    return APIResponse(
        success=True,
        data=CourseInsightsResponse(
            course_id=course.id,
            has_evidence=has_evidence,
            cohort_mastery=cohort,
            alerts=counts,
            review_queue=review_queue,
        ),
    )


@router.get(
    "/courses/{course_id}/effectiveness",
    response_model=APIResponse[EffectivenessResponse],
)
async def course_effectiveness(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[EffectivenessResponse]:
    """The teacher effectiveness tracker for an owned course (B8, pure read).

    The read side of the loop ``services/mastery.py::_close_follow_ups`` writes
    (Decision 9): the course's ``outcome_checks`` grouped by ``status`` and, via
    the ``OutcomeCheck → FollowUpAction`` join, by follow-up ``action_type``.
    ``get_owned_course`` 404s a non-owner; a course with no outcomes returns the
    designed empty payload (``has_evidence=false``). No new persistence, no job.
    """
    rows = (
        await db.execute(
            select(OutcomeCheck.status, FollowUpAction.action_type)
            .outerjoin(
                FollowUpAction,
                FollowUpAction.id == OutcomeCheck.follow_up_action_id,
            )
            .where(OutcomeCheck.course_id == course.id)
        )
    ).all()

    by_status: dict[str, int] = {s: 0 for s in _OUTCOME_STATUSES}
    groups: dict[str, dict[str, int]] = {}
    for status, action_type in rows:
        if status in by_status:
            by_status[status] += 1
        if action_type is not None:
            bucket = groups.setdefault(
                action_type, {s: 0 for s in _OUTCOME_STATUSES}
            )
            if status in bucket:
                bucket[status] += 1

    by_action_type = [
        EffectivenessActionGroup(
            action_type=action_type,
            total=sum(bucket.values()),
            by_status=bucket,
        )
        for action_type, bucket in sorted(groups.items())
    ]

    return APIResponse(
        success=True,
        data=EffectivenessResponse(
            course_id=course.id,
            has_evidence=len(rows) > 0,
            total=len(rows),
            by_status=by_status,
            by_action_type=by_action_type,
        ),
    )
