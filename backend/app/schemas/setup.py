"""Pydantic schemas for the course-setup wizard router (Task 8)."""
from pydantic import BaseModel


class SetupStepUpdate(BaseModel):
    step: str
    done: bool


class SetupStateResponse(BaseModel):
    setup_status: str
    context_status: str
    steps: dict[str, bool]
    missing: list[str]


class SetupAnalysisResponse(BaseModel):
    ready: bool
    analysis: dict | None = None
