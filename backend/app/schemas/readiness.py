"""Readiness funnel request/response schemas (spec §5 ``readiness.py``)."""
from typing import Any

from pydantic import BaseModel


class ReadinessSubmit(BaseModel):
    answers: dict[str, Any] = {}


class ReadinessResponseOut(BaseModel):
    phase: str
    status: str
    answers: dict[str, Any]
    result: dict[str, Any]

    model_config = {"from_attributes": True}


class ReadinessSummaryOut(BaseModel):
    completed_phases: list[str]
    recommendation: dict[str, Any] | None
    answers: dict[str, Any]


class CoursePreviewOut(BaseModel):
    id: str
    name: str
    code: str | None
    language: str
    description: str | None
    is_open: bool
    join_mode: str
    depth: str
    # Deep preview adds a schedule/ILO teaser (populated only when depth='deep').
    detail: dict[str, Any] | None = None
