"""Provisional placement scoring. Pure functions, no database, no I/O.

Every rule here is a transcription of the published scoring workbook
(``Meli_Placement_Test_v1.2_Scoring_and_Calibration.xlsx``), which is the
executable authority CLE has already verified against seven scenarios. Where
the Administrator Pack prose and the workbook formula disagree, the workbook
wins and the disagreement is called out in a comment, because the workbook is
what produced the evidence CLE signed off.

The single most important property of this module is what it does *not* do: it
never decides anything. It produces evidence and a provisional recommendation.
Authority to release lives in the attempt state machine and a CLE review row.

Workbook cell references appear in comments so a reviewer can diff a rule
against the spreadsheet without re-deriving it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

BANDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)
ITEMS_PER_BAND = 5
TOTAL_ITEMS = 30

#: Cumulative item count through band L, used as the denominator of the
#: sustained-performance test. Band 3 means bands 1+2+3 = 15 items.
_CUMULATIVE_ITEMS = {band: band * ITEMS_PER_BAND for band in BANDS}

#: Provisional course map (workbook ``Rules & Mapping``; Summary!B20).
#: Band 0 and 1 both map to LANG1511; 5 and 6 both map to LANG1515.
COURSE_BY_BAND: Mapping[int, str] = {
    0: "LANG1511",
    1: "LANG1511",
    2: "LANG1512",
    3: "LANG1513",
    4: "LANG1514",
    5: "LANG1515",
    6: "LANG1515",
}

SECTION_TOTALS: Mapping[str, int] = {
    "listening": 12,
    "language_use": 6,
    "reading": 12,
}

#: Flags that force ``confidence == "review"``.
#:
#: The three sources disagree slightly and the disagreement is resolved here
#: rather than silently:
#:
#: * the **workbook** (Summary!B23) forces review on five conditions;
#: * **Administrator Pack §5** states a seven-condition "Review required" list
#:   that additionally includes declared-background mismatch, technical
#:   interruption, repeated-response pattern and cross-attempt spread;
#: * the **integration spec** lists eight mandatory triggers, adding "legacy
#:   HSK5/6 reference result mapping to LANG1515".
#:
#: §5 is the normative policy statement and is a superset of the workbook, so
#: it is followed. The one exception is ``high_band_ceiling``: forcing review on
#: it would make a perfect 30/30 paper report "review required", contradicting
#: the workbook scenario CLE verified ("highest sustained band 6, provisional
#: LANG1515, confidence High"). It is therefore raised as advisory evidence --
#: it is genuinely useful, since this test cannot discriminate above band 5 --
#: without overriding a signed-off result.
#:
#: This costs nothing in safety: no attempt reaches a learner without a CLE
#: release either way. It only changes the confidence label and queue ordering.
REVIEW_FORCING_FLAGS: frozenset[str] = frozenset(
    {
        "incomplete_answers",
        "duration_too_short",
        "duration_too_long",
        "lower_band_break",
        "declared_background_mismatch",
        "technical_interruption",
        "form_compromised",
        "attempt_spread",
        "response_pattern_anomaly",
        "item_key_disputed",
    }
)

#: Interruption kinds the system records itself. They are evidence for a
#: reviewer but are not the learner's connection failing, so they must not
#: raise the technical-interruption trigger.
_SYSTEM_INTERRUPTION_KINDS: frozenset[str] = frozenset({"timer_expired"})

#: Raised as evidence, never as a confidence override. See above.
ADVISORY_FLAGS: frozenset[str] = frozenset({"high_band_ceiling"})


@dataclass(frozen=True)
class ScoringPolicy:
    """Versioned thresholds. Stored on the test version, never hardcoded live.

    The spec requires review thresholds to be "versioned configuration with
    audit history", so an attempt records which policy version scored it and a
    later tightening cannot silently reinterpret past results.
    """

    version: str = "v1.2-candidate"
    #: Minimum correct at the candidate band (workbook "Band minimum").
    band_minimum: int = 3
    #: Cumulative accuracy required through the candidate band.
    cumulative_threshold: float = 0.7
    #: Below this many answered items, automated confidence is withheld.
    incomplete_answers_below: int = 27
    #: Minutes. Strictly below is "too fast"; strictly above is "too long".
    fast_duration_minutes: int = 12
    long_duration_minutes: int = 45
    #: Declared-vs-measured band difference that triggers review.
    background_mismatch_bands: int = 1
    #: Course-band spread across a learner's attempts that triggers review.
    attempt_spread_bands: int = 1
    #: Share of answered items on one letter that reads as a response pattern.
    repeated_answer_share: float = 0.8
    #: An item answered faster than this is "impossibly fast" for this test.
    fast_item_ms: int = 2000
    #: Share of impossibly-fast items that triggers the pattern flag.
    fast_item_share: float = 0.5

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "ScoringPolicy":
        """Build from a stored ``review_policy`` blob, ignoring unknown keys.

        Unknown keys are dropped rather than raising: a newer version may add a
        threshold this build does not read yet, and refusing to score an
        existing attempt because of that would be worse than ignoring it.
        """
        if not config:
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in config.items() if k in known})


@dataclass(frozen=True)
class ScoredResponse:
    """One response paired with the item facts scoring needs."""

    question_number: int
    legacy_band: int
    section: str
    response: str | None
    correct_answer: str
    #: Excluded from scoring when the key is disputed; see ``score_attempt``.
    key_disputed: bool = False
    time_spent_ms: int | None = None


@dataclass(frozen=True)
class ScoreResult:
    raw_score: int
    answered_count: int
    scorable_count: int
    band_scores: dict[int, int]
    skill_scores: dict[str, dict[str, int]]
    highest_sustained_band: int
    provisional_course: str
    lower_band_break: bool
    clear_next_band_boundary: bool
    confidence: str
    review_flags: list[str] = field(default_factory=list)
    #: Human-readable evidence status per band, mirroring Summary!D11:D16.
    band_evidence: dict[int, str] = field(default_factory=dict)

    @property
    def requires_review(self) -> bool:
        return self.confidence == "review" or bool(self.review_flags)


_WHITESPACE_OR_DASH = re.compile(r"[-\s]+")


def normalise_response(value: str | None) -> str:
    """Fold a raw response to its comparison form.

    Mirrors Entry!G9's ``UPPER(SUBSTITUTE(SUBSTITUTE(x,"-","")," ",""))``, so
    ``"c-a-b"``, ``"C A B"`` and ``"CAB"`` all compare equal to key ``C-A-B``.
    """
    if value is None:
        return ""
    return _WHITESPACE_OR_DASH.sub("", value).strip().upper()


def is_correct(response: str | None, correct_answer: str) -> bool:
    """Whether a response matches the key. Blank is never correct."""
    normalised = normalise_response(response)
    if not normalised:
        return False
    return normalised == normalise_response(correct_answer)


def band_scores(responses: Iterable[ScoredResponse]) -> dict[int, int]:
    """Correct count per legacy band (Summary!B11:B16)."""
    scores = {band: 0 for band in BANDS}
    for item in responses:
        if item.key_disputed:
            continue
        if item.legacy_band in scores and is_correct(item.response, item.correct_answer):
            scores[item.legacy_band] += 1
    return scores


def skill_scores(responses: Iterable[ScoredResponse]) -> dict[str, dict[str, int]]:
    """Correct/total per section (Summary!G11:H13).

    ``total`` is the blueprint total, not the number scored, so a disputed item
    shows as a section the learner could not fully demonstrate rather than
    silently shrinking the denominator and inflating the percentage.
    """
    out = {
        section: {"correct": 0, "total": total}
        for section, total in SECTION_TOTALS.items()
    }
    for item in responses:
        bucket = out.get(item.section)
        if bucket is None or item.key_disputed:
            continue
        if is_correct(item.response, item.correct_answer):
            bucket["correct"] += 1
    return out


def highest_sustained_band(scores: Mapping[int, int], policy: ScoringPolicy) -> int:
    """The highest band with direct AND sustained evidence (Summary!B19).

    Two conditions, both required, checked from band 6 downwards:

    * at least ``band_minimum`` correct **at** that band; and
    * at least ``cumulative_threshold`` accuracy **through** that band.

    Band 1 is the interesting case: 3/5 satisfies the minimum but 3/5 = 0.6 is
    below 0.7, so band 1 in practice needs 4/5. The workbook notes this
    explicitly ("Requires 4/5 at Band 1") and it is a property of the two rules
    interacting, not a special case.
    """
    for band in sorted(BANDS, reverse=True):
        at_band = scores.get(band, 0)
        if at_band < policy.band_minimum:
            continue
        through = sum(scores.get(b, 0) for b in BANDS if b <= band)
        if through / _CUMULATIVE_ITEMS[band] >= policy.cumulative_threshold:
            return band
    return 0


def has_lower_band_break(scores: Mapping[int, int], sustained: int) -> bool:
    """Whether any band *below* the sustained band is weak (Summary!B21).

    A learner who sustains band 4 but scored 2/5 at band 2 has a non-monotonic
    profile: the result is not a clean level, so it goes to review rather than
    being placed either up or down automatically.
    """
    if sustained <= 1:
        return False
    return any(scores.get(band, 0) <= 2 for band in BANDS if band < sustained)


def has_clear_next_band_boundary(scores: Mapping[int, int], sustained: int) -> bool:
    """Whether the band above the sustained one is clearly not reached (B22).

    Band 6 is ``True`` by definition: there is no band 7 to fail, so the ceiling
    is the test's own ceiling.
    """
    if sustained == 0:
        return False
    if sustained == 6:
        return True
    return scores.get(sustained + 1, 0) <= 2


def band_evidence_labels(scores: Mapping[int, int]) -> dict[int, str]:
    """Words, not numbers, per band (Summary!D11:D16)."""
    labels: dict[int, str] = {}
    for band in BANDS:
        value = scores.get(band, 0)
        if value >= 4:
            labels[band] = "strong"
        elif value == 3:
            labels[band] = "developing"
        else:
            labels[band] = "not_demonstrated"
    return labels


def score_attempt(
    responses: Sequence[ScoredResponse],
    *,
    duration_seconds: int | None,
    policy: ScoringPolicy | None = None,
    declared_band: int | None = None,
    interruptions: Sequence[Mapping[str, Any]] = (),
    prior_attempt_bands: Sequence[int] = (),
    accommodation: Mapping[str, Any] | None = None,
    form_compromised: bool = False,
) -> ScoreResult:
    """Produce the full evidence bundle for one submitted attempt.

    Disputed items are excluded from the numerator but still raise a review
    flag. Scoring an item whose key the content owner has rejected would
    manufacture a number nobody can defend; dropping it silently would hide
    that the learner's result rests on 29 items, not 30.
    """
    policy = policy or ScoringPolicy()

    scorable = [item for item in responses if not item.key_disputed]
    scores = band_scores(responses)
    raw = sum(scores.values())
    # Answered counts every response the learner gave, including on a disputed
    # item: they did the work, and the completion triggers are about effort.
    answered = sum(1 for item in responses if normalise_response(item.response))

    sustained = highest_sustained_band(scores, policy)
    break_below = has_lower_band_break(scores, sustained)
    clear_boundary = has_clear_next_band_boundary(scores, sustained)

    flags = _review_flags(
        responses=responses,
        scores=scores,
        answered=answered,
        sustained=sustained,
        lower_break=break_below,
        duration_seconds=duration_seconds,
        policy=policy,
        declared_band=declared_band,
        interruptions=interruptions,
        prior_attempt_bands=prior_attempt_bands,
        accommodation=accommodation,
        form_compromised=form_compromised,
    )

    confidence = _confidence(
        scores=scores,
        answered=answered,
        sustained=sustained,
        lower_break=break_below,
        clear_boundary=clear_boundary,
        duration_seconds=duration_seconds,
        policy=policy,
        flags=flags,
    )

    return ScoreResult(
        raw_score=raw,
        answered_count=answered,
        scorable_count=len(scorable),
        band_scores=scores,
        skill_scores=skill_scores(responses),
        highest_sustained_band=sustained,
        provisional_course=COURSE_BY_BAND[sustained],
        lower_band_break=break_below,
        clear_next_band_boundary=clear_boundary,
        confidence=confidence,
        review_flags=flags,
        band_evidence=band_evidence_labels(scores),
    )


def _duration_minutes(duration_seconds: int | None) -> float | None:
    if duration_seconds is None:
        return None
    return duration_seconds / 60.0


def _confidence(
    *,
    scores: Mapping[int, int],
    answered: int,
    sustained: int,
    lower_break: bool,
    clear_boundary: bool,
    duration_seconds: int | None,
    policy: ScoringPolicy,
    flags: Sequence[str],
) -> str:
    """Summary!B23, extended by the review-forcing system triggers.

    The workbook sees one attempt and has no telemetry, so its review branch
    covers five conditions. The system-level ones (technical interruption,
    cross-attempt spread, response pattern, disputed key) are added per
    Administrator Pack §5, which lists them as "Review required".

    Only flags in :data:`REVIEW_FORCING_FLAGS` count. Advisory flags are
    evidence for the reviewer and deliberately do not override the workbook's
    verified confidence output.
    """
    minutes = _duration_minutes(duration_seconds)

    # Every condition below is already expressed as a flag, so the flag list is
    # the single source of truth. Duplicating the duration tests here meant an
    # approved extended-time accommodation suppressed the FLAG but not the
    # confidence: the learner landed in review with an empty flag list, and the
    # reviewer's "why this needs review" panel rendered nothing at all.
    if (
        sustained == 0
        or any(flag in REVIEW_FORCING_FLAGS for flag in flags)
    ):
        return "review"

    at_band = scores.get(sustained, 0)
    if answered == TOTAL_ITEMS and clear_boundary and at_band >= 4:
        return "high"
    return "medium"


def _review_flags(
    *,
    responses: Sequence[ScoredResponse],
    scores: Mapping[int, int],
    answered: int,
    sustained: int,
    lower_break: bool,
    duration_seconds: int | None,
    policy: ScoringPolicy,
    declared_band: int | None,
    interruptions: Sequence[Mapping[str, Any]],
    prior_attempt_bands: Sequence[int],
    accommodation: Mapping[str, Any] | None,
    form_compromised: bool,
) -> list[str]:
    """The eight mandatory review triggers, as machine codes.

    Codes are never shown raw to a learner; the UI maps them to copy. Ordering
    is stable so an evidence-bundle hash is reproducible.
    """
    flags: list[str] = []
    minutes = _duration_minutes(duration_seconds)
    extended_time = bool((accommodation or {}).get("extended_time"))

    # 1. Incomplete.
    if answered < policy.incomplete_answers_below:
        flags.append("incomplete_answers")

    # 2. Duration outside the plausible band. An approved extended-time
    #    accommodation explains a long sitting, so it suppresses only the long
    #    trigger -- it can never explain an impossibly fast one.
    if minutes is not None:
        if minutes < policy.fast_duration_minutes:
            flags.append("duration_too_short")
        if minutes > policy.long_duration_minutes and not extended_time:
            flags.append("duration_too_long")

    # 3. Non-monotonic profile.
    if lower_break:
        flags.append("lower_band_break")

    # 4. Declared background far from measured.
    if declared_band is not None and abs(declared_band - sustained) > policy.background_mismatch_bands:
        flags.append("declared_background_mismatch")

    # 5. Technical: interruption, missing audio, or a compromised form.
    #    System-generated markers are excluded. The expiry sweep records its own
    #    `timer_expired` entry, and counting that as a technical interruption
    #    told every reviewer that a sitting was disrupted when the learner had
    #    simply run out of time -- corrupting the evidence they reason from.
    if any(
        (event or {}).get("kind") not in _SYSTEM_INTERRUPTION_KINDS
        for event in interruptions
    ):
        flags.append("technical_interruption")
    if form_compromised:
        flags.append("form_compromised")

    # 6. Cross-attempt instability, measured in course bands rather than raw
    #    score: two attempts differing by one band map to adjacent courses,
    #    which is normal; more than one is not.
    if prior_attempt_bands:
        spread = max([sustained, *prior_attempt_bands]) - min([sustained, *prior_attempt_bands])
        if spread > policy.attempt_spread_bands:
            flags.append("attempt_spread")

    # 7. Response-pattern anomalies.
    if _has_response_pattern_anomaly(responses, policy):
        flags.append("response_pattern_anomaly")

    # 8. A legacy HSK5/6 result maps to the ceiling course, so the boundary
    #    cannot be evidenced by this test and needs a human look.
    if sustained >= 5:
        flags.append("high_band_ceiling")

    # Not one of the eight, but it invalidates the arithmetic: an item whose key
    # the content owner disputes cannot contribute a defensible point.
    if any(item.key_disputed for item in responses):
        flags.append("item_key_disputed")

    return flags


def _has_response_pattern_anomaly(
    responses: Sequence[ScoredResponse], policy: ScoringPolicy
) -> bool:
    """Detect straight-lining or impossibly fast answering.

    Deliberately coarse. This flag routes an attempt to a human; it is not an
    accusation, and the thresholds are versioned config so CLE can tune them
    against pilot data rather than argue with a constant in code.
    """
    answered = [item for item in responses if normalise_response(item.response)]
    if len(answered) < 10:
        # Too few responses to distinguish a pattern from a short sitting; the
        # incomplete trigger already covers this case.
        return False

    counts: dict[str, int] = {}
    for item in answered:
        letter = normalise_response(item.response)
        counts[letter] = counts.get(letter, 0) + 1
    if max(counts.values()) / len(answered) >= policy.repeated_answer_share:
        return True

    timed = [item for item in answered if item.time_spent_ms is not None]
    if timed:
        fast = sum(1 for item in timed if (item.time_spent_ms or 0) < policy.fast_item_ms)
        if fast / len(timed) >= policy.fast_item_share:
            return True
    return False
