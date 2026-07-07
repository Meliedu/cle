"""Response schemas for the pure-read insights surface (P6).

These reshape existing evidence rows; they carry NO new computed fields beyond
grouping. The learning profile groups the caller's ``concept_mastery`` rows.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ConceptMasteryEntry(BaseModel):
    """One reshaped ``concept_mastery`` row (values read as-is, never recomputed)."""

    concept_id: uuid.UUID
    concept_name: str
    mastery_score: Decimal
    confidence: Decimal
    attempt_count: int
    last_attempt_at: datetime | None


class LearningProfileGroups(BaseModel):
    """Concepts bucketed by the mastery/confidence thresholds ``api/mastery.py`` uses."""

    strong: list[ConceptMasteryEntry]
    developing: list[ConceptMasteryEntry]
    weak: list[ConceptMasteryEntry]


class LearningProfileResponse(BaseModel):
    """The caller's learning profile for one course.

    ``has_evidence`` is the discriminator the frontend uses to choose between the
    profile view and the designed no-evidence state (Decision 6): it is ``False``
    when there is no confident evidence (zero rows, or every row still below the
    ``confidence >= 0.5`` gate). ``disclaimer`` is the pilot
    ``claim_limits['learning_profile']`` copy, returned verbatim.
    """

    course_id: uuid.UUID
    has_evidence: bool
    concept_count: int
    groups: LearningProfileGroups
    disclaimer: str
