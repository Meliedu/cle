"""Typed pilot profile: everything institution-specific lives here, not in code."""
from typing import Literal

from pydantic import BaseModel, Field


class ConfidenceScale(BaseModel):
    min: int
    max: int
    labels: dict[int, str]


class ScoreCategoryDefault(BaseModel):
    name: str
    weight: float | None = None


class ReadinessQuestion(BaseModel):
    id: str
    kind: Literal["single_choice", "multi_choice", "scale", "short_text"]
    prompt: str
    options: list[str] = Field(default_factory=list)


class ReadinessPhaseDef(BaseModel):
    phase: Literal["eligibility_survey", "ready_check", "diagnostic"]
    title: str
    intro: str
    questions: list[ReadinessQuestion]


class ReportCadence(BaseModel):
    weekly: bool
    end_term: bool


class PilotProfile(BaseModel):
    id: str
    institution: str
    course_family: str
    terminology: dict[str, str]
    skill_taxonomy: list[str]
    confidence_scale: ConfidenceScale
    score_category_defaults: list[ScoreCategoryDefault]
    readiness: list[ReadinessPhaseDef]
    report_cadence: ReportCadence
    role_rules: dict[str, str]  # email domain -> role
    locales: list[str]
    claim_limits: dict[str, str]  # context key -> student-facing limit copy
