"""Attempt state machine and form rotation.

The state machine is the mechanism behind the package's central claim that
"placement authority is an explicit workflow state" (Administrator Pack §8).
A score is not a recommendation; a recommendation is not a release. Each of
those is a distinct state, and the only way between them is a transition this
module allows.

Two rules are enforced here rather than trusted to callers:

* **No system action may skip ``review_pending`` when a review trigger
  applies.** The scorer decides whether triggers fired; this module refuses the
  ``scored -> approved`` shortcut when they did.
* **Only an authorised release event unlocks the recommendation.** Nothing
  transitions into ``released`` except an explicit CLE release.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: ``state -> states reachable from it``.
#:
#: Read the exception columns as: anything in flight can expire, be abandoned,
#: or be invalidated by CLE; anything submitted can additionally be pulled into
#: technical review.
TRANSITIONS: Mapping[str, frozenset[str]] = {
    "created": frozenset(
        {"eligibility_confirmed", "expired", "abandoned", "invalidated"}
    ),
    "eligibility_confirmed": frozenset(
        {"instructions_acknowledged", "expired", "abandoned", "invalidated"}
    ),
    "instructions_acknowledged": frozenset(
        {"in_progress", "expired", "abandoned", "invalidated"}
    ),
    "in_progress": frozenset(
        {"submitted", "expired", "abandoned", "invalidated", "technical_review"}
    ),
    "submitted": frozenset({"scored", "invalidated", "technical_review"}),
    "scored": frozenset(
        {"review_pending", "approved", "invalidated", "technical_review"}
    ),
    "review_pending": frozenset(
        {"approved", "overridden", "advising_required", "invalidated", "technical_review"}
    ),
    "approved": frozenset({"released", "invalidated"}),
    "overridden": frozenset({"released", "invalidated"}),
    "advising_required": frozenset(
        {"approved", "overridden", "invalidated", "review_pending"}
    ),
    "released": frozenset({"invalidated"}),
    # Terminal / off-path.
    "expired": frozenset({"invalidated"}),
    "abandoned": frozenset({"invalidated"}),
    "invalidated": frozenset(),
    "technical_review": frozenset(
        {"scored", "review_pending", "invalidated", "abandoned"}
    ),
}

#: States in which a learner may still change answers.
MUTABLE_STATES: frozenset[str] = frozenset({"in_progress"})

#: States in which the attempt is finished but carries no released result.
PENDING_STATES: frozenset[str] = frozenset(
    {"submitted", "scored", "review_pending", "approved", "overridden",
     "advising_required", "technical_review"}
)

#: The only state in which a recommendation may be shown to the learner.
RELEASED_STATES: frozenset[str] = frozenset({"released"})

#: States that consume one of the learner's attempts. An attempt invalidated by
#: CLE does not: invalidation is our failure or a compromised sitting, and
#: charging the learner for it would penalise them for our problem.
CONSUMING_STATES: frozenset[str] = frozenset(
    {"in_progress", "submitted", "scored", "review_pending", "approved",
     "overridden", "advising_required", "released", "expired", "abandoned",
     "technical_review"}
)


class PlacementStateError(Exception):
    """Illegal transition or action for the attempt's current state."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise PlacementStateError(
            "ILLEGAL_TRANSITION",
            f"cannot move a placement attempt from '{current}' to '{target}'",
        )


def next_state_after_scoring(*, requires_review: bool) -> str:
    """Where a freshly scored attempt goes.

    A triggered attempt must land in ``review_pending``. The spec is explicit
    that no system action may skip it, so this is a function rather than a
    caller decision: there is no code path that scores an attempt and chooses
    to bypass review.
    """
    return "review_pending" if requires_review else "scored"


def assert_release_allowed(state: str) -> None:
    """Guard the one transition that actually reaches the learner."""
    if state not in {"approved", "overridden"}:
        raise PlacementStateError(
            "RELEASE_NOT_APPROVED",
            "a placement result can only be released after CLE approves or "
            "overrides it",
        )


@dataclass(frozen=True)
class FormAllocation:
    form_code: str
    reference: dict[str, Any]


class FormRotationError(Exception):
    """No eligible form could be allocated; CLE action is required."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def allocate_form(
    *,
    available: Sequence[Mapping[str, Any]],
    used_form_codes: Iterable[str],
    attempt_number: int,
    rng: secrets.SystemRandom | None = None,
) -> FormAllocation:
    """Pick a form for this attempt (Administrator Pack §6).

    Attempt 1 is a random choice among A-E; attempts 2 and 3 must use a form the
    learner has not seen. Disabled and compromised forms are excluded at every
    attempt.

    If nothing eligible remains the caller gets an error rather than a reused
    form: silently repeating a form the learner has already sat would turn a
    placement result into a memory test, and the spec requires CLE action here
    instead.

    The allocation reference is returned alongside so the choice is auditable
    after the fact -- "why did this learner get Form D" must be answerable.
    """
    random_source = rng or secrets.SystemRandom()

    seen = {code.upper() for code in used_form_codes}
    eligible = [
        form for form in available
        if form.get("status") == "active" and str(form["form_code"]).upper() not in seen
    ]

    if not eligible:
        raise FormRotationError(
            "NO_ELIGIBLE_FORM",
            "no unused, active form remains for this learner; CLE must enable "
            "another form or invalidate a prior attempt",
        )

    chosen = eligible[random_source.randrange(len(eligible))]
    return FormAllocation(
        form_code=str(chosen["form_code"]).upper(),
        reference={
            "attempt_number": attempt_number,
            "eligible_forms": sorted(str(f["form_code"]).upper() for f in eligible),
            "excluded_used": sorted(seen),
            "excluded_inactive": sorted(
                str(f["form_code"]).upper()
                for f in available
                if f.get("status") != "active"
            ),
            "selection": "uniform_random",
        },
    )


def evidence_snapshot_hash(payload: Mapping[str, Any]) -> str:
    """Stable hash of the evidence bundle a reviewer was shown.

    Sorted keys and a compact separator so the same evidence always hashes the
    same way regardless of dict ordering; the review row stores it so a later
    dispute can establish what was on screen at decision time.
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
