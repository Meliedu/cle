"""Materialise top-10 next_actions for a (user, course).

Cycle:
  1. resolve engine_variant
  2. outer_fringe_concepts → fallback to weakest-3 if empty
  3. expand each concept into candidate (action_type, target) tuples
  4. score each via app.services.scoring
  5. delete unconsumed existing rows for (user, course)
  6. insert top 10 with expires_at = now() + 1 hour, engine_variant set
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    AssignmentSubmission,
    Concept,
    ConceptMastery,
    ConceptTag,
    CourseMeeting,
    FlashcardCard,
    FlashcardProgress,
    FlashcardSet,
    NextAction,
)
from app.services.engine_mode import resolve_engine_mode
from app.services.outer_fringe import outer_fringe_concepts
from app.services.scoring import (
    score_complete_assignment,
    score_flashcard_review,
    score_practice_weakness,
    score_prep_meeting,
)

TTL_HOURS = 1
TOP_N = 10
DEADLINE_HORIZON_DAYS = 7
LAZY_REFRESH_MINUTES = 30


@dataclass
class _Candidate:
    action_type: str
    target_kind: str | None
    target_id: uuid.UUID | None
    priority_score: float
    candidate_source: str
    reason: dict


async def _expand_concept_candidates(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    concept_id: uuid.UUID,
    concept_name: str,
    mastery: float,
    confidence: float,
    now: datetime,
) -> list[_Candidate]:
    out: list[_Candidate] = []

    # 1. practice_weakness on the concept itself
    s = score_practice_weakness(mastery=mastery, confidence=confidence)
    if s > 0:
        out.append(
            _Candidate(
                action_type="practice_weakness",
                target_kind="concept",
                target_id=concept_id,
                priority_score=s,
                candidate_source="outer_fringe",
                reason={
                    "concept_name": concept_name,
                    "mastery": mastery,
                    "confidence": confidence,
                },
            )
        )

    # 2. prep_meeting / complete_assignment for upcoming items tagged with this concept
    horizon = now + timedelta(days=DEADLINE_HORIZON_DAYS)

    # Upcoming meetings tagged with this concept.
    meetings = (
        await db.execute(
            select(CourseMeeting, ConceptTag.weight)
            .join(ConceptTag, and_(
                ConceptTag.target_kind == "meeting",
                ConceptTag.target_id == CourseMeeting.id,
            ))
            .where(
                ConceptTag.concept_id == concept_id,
                CourseMeeting.course_id == course_id,
                CourseMeeting.deleted_at.is_(None),
                CourseMeeting.scheduled_at.between(now, horizon),
            )
        )
    ).all()
    for meeting, tag_weight in meetings:
        days = (meeting.scheduled_at - now).total_seconds() / 86400.0
        s = score_prep_meeting(
            meeting_concept_weights=[(float(tag_weight), mastery)],
            days_until_meeting=max(0.0, days),
        )
        if s > 0:
            out.append(
                _Candidate(
                    action_type="prep_meeting",
                    target_kind="course_meeting",
                    target_id=meeting.id,
                    priority_score=s,
                    candidate_source="deadline",
                    reason={
                        "concept_name": concept_name,
                        "meeting_title": meeting.title,
                        "scheduled_at": meeting.scheduled_at.isoformat(),
                        "days_until": days,
                    },
                )
            )

    # Upcoming assignments tagged with this concept that the user has NOT submitted.
    submitted_subq = (
        select(AssignmentSubmission.assignment_id).where(
            AssignmentSubmission.user_id == user_id,
            AssignmentSubmission.status.in_(("submitted", "graded")),
        )
    )
    assignments = (
        await db.execute(
            select(Assignment)
            .join(ConceptTag, and_(
                ConceptTag.target_kind == "assignment",
                ConceptTag.target_id == Assignment.id,
            ))
            .where(
                ConceptTag.concept_id == concept_id,
                Assignment.course_id == course_id,
                Assignment.deleted_at.is_(None),
                Assignment.is_published.is_(True),
                Assignment.due_at.between(now, horizon),
                Assignment.id.not_in(submitted_subq),
            )
        )
    ).scalars().all()
    for asn in assignments:
        days = (asn.due_at - now).total_seconds() / 86400.0
        s = score_complete_assignment(
            assignment_weight=asn.weight or Decimal("1.00"),
            days_until_due=max(0.0, days),
        )
        if s > 0:
            out.append(
                _Candidate(
                    action_type="complete_assignment",
                    target_kind="assignment",
                    target_id=asn.id,
                    priority_score=s,
                    candidate_source="deadline",
                    reason={
                        "concept_name": concept_name,
                        "assignment_title": asn.title,
                        "due_at": asn.due_at.isoformat(),
                        "days_until": days,
                    },
                )
            )

    return out


async def _flashcard_review_candidates(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    now: datetime,
) -> list[_Candidate]:
    """One catch-all flashcard_review candidate per course if anything is due."""
    due_count = (
        await db.execute(
            select(func.count())
            .select_from(FlashcardProgress)
            .join(FlashcardCard, FlashcardCard.id == FlashcardProgress.flashcard_card_id)
            .join(FlashcardSet, FlashcardSet.id == FlashcardCard.flashcard_set_id)
            .where(
                FlashcardProgress.user_id == user_id,
                FlashcardSet.course_id == course_id,
                FlashcardSet.is_published.is_(True),
                FlashcardProgress.next_review.is_not(None),
                FlashcardProgress.next_review <= now,
            )
        )
    ).scalar_one()
    if not due_count:
        return []
    # Cap due-count at 6000 so 1.5 × 6000 = 9000 stays safely under
    # the NUMERIC(7,3) ceiling of 9999.999. Any student with 6000+
    # due cards has the recommendation pinned to the top regardless;
    # clamping at 6000 sacrifices nothing for stability.
    capped_due = min(int(due_count), 6000)
    s = score_flashcard_review(cards_due_count=capped_due)
    return [
        _Candidate(
            action_type="flashcard_review",
            target_kind=None,
            target_id=None,
            priority_score=s,
            candidate_source="review",
            reason={"cards_due": int(due_count)},
        )
    ]


async def materialize_next_actions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    now: datetime | None = None,
) -> list[NextAction]:
    now = now or datetime.now(timezone.utc)
    # Serialize concurrent materialize calls for the same (user, course).
    # Two workers (e.g. one from an attempt event + one from the daily horizon
    # scan) can otherwise both DELETE then both INSERT, leaving 20 stale rows.
    # Hash to a 63-bit signed bigint (Postgres advisory keys are bigint).
    # The lock auto-releases at transaction commit.
    from sqlalchemy import text as _text
    lock_key = (
        int.from_bytes(user_id.bytes, "big") ^ int.from_bytes(course_id.bytes, "big")
    ) & 0x7FFFFFFFFFFFFFFF
    await db.execute(_text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})
    variant = await resolve_engine_mode(db, user_id=user_id, course_id=course_id)
    if variant == "off":
        # Drop any stale unconsumed rows so the off-arm UI is clean.
        await db.execute(
            delete(NextAction).where(
                NextAction.user_id == user_id,
                NextAction.course_id == course_id,
                NextAction.consumed_at.is_(None),
            )
        )
        await db.commit()
        return []

    fringe = await outer_fringe_concepts(db, user_id=user_id, course_id=course_id)
    candidates: list[_Candidate] = []

    if not fringe:
        # Fallback: weakest 3 concepts the student has any evidence on.
        rows = (
            await db.execute(
                select(ConceptMastery, Concept.name)
                .join(Concept, Concept.id == ConceptMastery.concept_id)
                .where(
                    ConceptMastery.user_id == user_id,
                    ConceptMastery.course_id == course_id,
                    Concept.deleted_at.is_(None),
                    Concept.canonical_id.is_(None),
                )
                .order_by(ConceptMastery.mastery_score.asc())
                .limit(3)
            )
        ).all()
        for m, name in rows:
            s = score_practice_weakness(
                mastery=float(m.mastery_score), confidence=float(m.confidence)
            )
            if s > 0:
                candidates.append(
                    _Candidate(
                        action_type="practice_weakness",
                        target_kind="concept",
                        target_id=m.concept_id,
                        priority_score=s,
                        candidate_source="fallback",
                        reason={
                            "concept_name": name,
                            "mastery": float(m.mastery_score),
                            "confidence": float(m.confidence),
                        },
                    )
                )
    else:
        for fc in fringe:
            candidates.extend(
                await _expand_concept_candidates(
                    db,
                    user_id=user_id,
                    course_id=course_id,
                    concept_id=fc.concept_id,
                    concept_name=fc.name,
                    mastery=fc.current_mastery,
                    confidence=fc.current_confidence,
                    now=now,
                )
            )

    candidates.extend(
        await _flashcard_review_candidates(
            db, user_id=user_id, course_id=course_id, now=now
        )
    )

    # Replace existing unconsumed cache rows.
    await db.execute(
        delete(NextAction).where(
            NextAction.user_id == user_id,
            NextAction.course_id == course_id,
            NextAction.consumed_at.is_(None),
        )
    )

    # Top N by priority_score desc.
    top = sorted(candidates, key=lambda c: -c.priority_score)[:TOP_N]
    expires_at = now + timedelta(hours=TTL_HOURS)
    rows = [
        NextAction(
            user_id=user_id,
            course_id=course_id,
            action_type=c.action_type,
            target_kind=c.target_kind,
            target_id=c.target_id,
            priority_score=Decimal(f"{c.priority_score:.3f}"),
            candidate_source=c.candidate_source,
            reason=c.reason,
            expires_at=expires_at,
            engine_variant=variant,
        )
        for c in top
    ]
    db.add_all(rows)
    await db.commit()
    for r in rows:
        await db.refresh(r)
    return rows


async def get_or_recompute_next_actions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> list[NextAction]:
    """Return cached rows if any are < 30 min old; else materialise fresh."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(minutes=LAZY_REFRESH_MINUTES)
    cached = (
        await db.execute(
            select(NextAction)
            .where(
                NextAction.user_id == user_id,
                NextAction.course_id == course_id,
                NextAction.consumed_at.is_(None),
                NextAction.expires_at > now,
                NextAction.created_at >= threshold,
            )
            .order_by(NextAction.priority_score.desc())
        )
    ).scalars().all()
    if cached:
        return list(cached)
    return await materialize_next_actions(db, user_id=user_id, course_id=course_id, now=now)


async def record_serve(
    db: AsyncSession, action_ids: Iterable[uuid.UUID]
) -> list[NextAction]:
    """Stamp ``served_at = now()`` on each row that hasn't been served yet.

    Idempotent: rows with a non-null ``served_at`` are left alone.
    """
    ids = [i for i in action_ids if i is not None]
    if not ids:
        return []
    now = datetime.now(timezone.utc)
    await db.execute(
        update(NextAction)
        .where(
            NextAction.id.in_(ids),
            NextAction.served_at.is_(None),
        )
        .values(served_at=now)
    )
    await db.commit()
    rows = (
        await db.execute(
            select(NextAction).where(NextAction.id.in_(ids))
        )
    ).scalars().all()
    return list(rows)
