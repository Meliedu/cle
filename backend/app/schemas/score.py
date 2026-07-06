"""Pydantic schemas for the score-category CRUD router (T024 score-policy step).

P1 subset of the spec ``scores.py``. Grade export + student scores are P5.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ScoreCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    weight: Decimal | None = Field(default=None, ge=0, le=Decimal("999.99"))
    points_pool: Decimal | None = Field(default=None, ge=0, le=Decimal("999999.99"))
    # Omit to append at the end (next sort). Provide to place explicitly.
    sort: int | None = Field(default=None, ge=0)


class ScoreCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    weight: Decimal | None = Field(default=None, ge=0, le=Decimal("999.99"))
    points_pool: Decimal | None = Field(default=None, ge=0, le=Decimal("999999.99"))
    # Included so the teacher can reorder categories via PATCH (no separate
    # reorder endpoint in the P1 subset).
    sort: int | None = Field(default=None, ge=0)


class ScoreCategoryResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    name: str
    weight: Decimal | None
    points_pool: Decimal | None
    sort: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
