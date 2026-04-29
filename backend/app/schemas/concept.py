import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ConceptStatus = Literal["pending", "approved", "rejected", "merged"]
ConceptTargetKind = Literal[
    "chunk", "question", "flashcard_card", "pronunciation_item",
    "pool_item", "objective", "meeting", "assignment",
]
MeetingRole = Literal["introduced", "covered", "reinforced"]


class ConceptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    instructor_curated: bool = True


class ConceptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: ConceptStatus | None = None
    canonical_id: uuid.UUID | None = None
    instructor_curated: bool | None = None


class ConceptResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    name: str
    description: str | None
    canonical_id: uuid.UUID | None
    instructor_curated: bool
    status: ConceptStatus
    extracted_from_chunk_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConceptPrerequisiteCreate(BaseModel):
    prereq_concept_id: uuid.UUID
    dependent_concept_id: uuid.UUID
    strength: Decimal = Field(default=Decimal("1.00"), ge=0, le=1)


class ConceptPrerequisiteResponse(BaseModel):
    prereq_concept_id: uuid.UUID
    dependent_concept_id: uuid.UUID
    strength: Decimal
    instructor_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ConceptTagCreate(BaseModel):
    target_kind: ConceptTargetKind
    target_id: uuid.UUID
    weight: Decimal = Field(default=Decimal("1.00"), ge=0, le=1)
    role: MeetingRole | None = None


class ConceptTagResponse(BaseModel):
    concept_id: uuid.UUID
    target_kind: ConceptTargetKind
    target_id: uuid.UUID
    weight: Decimal
    role: MeetingRole | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConceptClusterMember(BaseModel):
    """A candidate concept inside a cluster awaiting curation."""
    candidate_id: uuid.UUID
    name: str
    description: str | None
    evidence_chunk_id: uuid.UUID | None


class ConceptClusterResponse(BaseModel):
    """One cluster the instructor curates as a unit."""
    cluster_id: uuid.UUID
    course_id: uuid.UUID
    suggested_name: str
    suggested_description: str | None
    members: list[ConceptClusterMember]
    example_chunk_ids: list[uuid.UUID]
    status: Literal["pending", "approved", "merged", "rejected"]


class ConceptClusterDecision(BaseModel):
    """Instructor curation action on a cluster."""
    action: Literal["approve", "rename", "merge", "reject"]
    final_name: str | None = None         # required when action='approve' or 'rename'
    final_description: str | None = None
    merge_into_concept_id: uuid.UUID | None = None  # required when action='merge'


class MasteryResponse(BaseModel):
    concept_id: uuid.UUID
    concept_name: str
    course_id: uuid.UUID
    alpha: Decimal
    beta: Decimal
    mastery_score: Decimal
    confidence: Decimal
    attempt_count: int
    last_attempt_at: datetime | None
    last_decay_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CohortMasteryRow(BaseModel):
    concept_id: uuid.UUID
    concept_name: str
    avg_mastery: float | None
    weak_students: int
    total_students_with_evidence: int
