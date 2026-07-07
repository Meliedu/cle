"""Score-policy publish gate (P5 B4, Decision 7).

A graded quiz or score-bearing activity may only be published once its grade
policy is fully specified. ``assert_score_policy_complete`` is the shared,
**pure** gate that enforces this: no DB access, no HTTP resolution, no commit.
It duck-types the required publish-settings off ANY artifact exposing them
(``Quiz`` from B1, ``Activity`` from B3) and raises a typed
``SCORE_POLICY_INCOMPLETE`` 422 listing EXACTLY the absent required fields.

Mirrors the checkpoint typed-gate envelope in ``api/checkpoints.py`` (§3.4:
``{"code": ..., "message": ...}``) but with HTTP 422 plus a ``missing`` list the
FE (F3) maps to a ``StateBanner tone="blocked"`` with jump-to-field affordances.

The function ALWAYS checks — being a NO-OP is the CALLER's responsibility:
practice quizzes and participation-only activities simply never invoke it.
"""

from typing import Any

from fastapi import HTTPException

# The publish-settings a graded/score-bearing artifact must carry. Order here is
# the order reported in ``missing`` so B5/B8 raise consistently and F3 can map
# each name to a field. A deadline is satisfied by EITHER ``due_at`` OR
# ``close_at``; when both are absent a single ``"deadline"`` entry is reported.
_REQUIRED_SCALAR_FIELDS = ("score_category_id", "points", "grading_mode")
_DEADLINE_FIELDS = ("due_at", "close_at")
_DEADLINE_MISSING_NAME = "deadline"


def assert_score_policy_complete(artifact: Any) -> None:
    """Raise ``SCORE_POLICY_INCOMPLETE`` (422) if any required field is absent.

    Works on both ``Quiz`` and ``Activity`` via duck-typed attribute reads. An
    attribute that is missing entirely or set to ``None`` counts as absent.
    Returns ``None`` when the artifact is fully specified.

    :param artifact: any object exposing the publish-settings attributes
        (``score_category_id``, ``points``, ``grading_mode``, ``due_at``,
        ``close_at``).
    :raises HTTPException: 422 with
        ``{"code": "SCORE_POLICY_INCOMPLETE", "message": ..., "missing": [...]}``
        when one or more required fields are absent.
    """
    missing: list[str] = [
        field
        for field in _REQUIRED_SCALAR_FIELDS
        if getattr(artifact, field, None) is None
    ]

    has_deadline = any(
        getattr(artifact, field, None) is not None for field in _DEADLINE_FIELDS
    )
    if not has_deadline:
        missing.append(_DEADLINE_MISSING_NAME)

    if not missing:
        return None

    raise HTTPException(
        status_code=422,  # UNPROCESSABLE (matches service-layer precedent)
        detail={
            "code": "SCORE_POLICY_INCOMPLETE",
            "message": (
                "This graded artifact cannot be published until its score policy "
                "is complete. Missing: " + ", ".join(missing) + "."
            ),
            "missing": missing,
        },
    )
