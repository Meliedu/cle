"""Report schemas (P7 Tasks B5–B7).

Response/request models for the teacher report surface over the ``reports`` table
(spec §4.9, Decision 2/3). ``ReportResponse`` serves BOTH the archive list and
the detail read — the archive is just a filtered list of the same shape, so the
frontend renders one card component for both.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ReportAudience = Literal["student", "teacher"]
ReportPeriod = Literal["weekly", "end_term"]
ReportStatus = Literal["draft", "reviewed", "sent", "archived"]


class ReportResponse(BaseModel):
    """Full report row (archive item + detail). ``body`` is the typed JSONB
    section payload (summary / completed work / weak points / next actions /
    claim limits); ``evidence_refs`` are the reviewed ``LearningNote`` ids the
    body was drafted from (Decision 1)."""

    id: uuid.UUID
    course_id: uuid.UUID
    audience: ReportAudience
    user_id: uuid.UUID | None
    period: ReportPeriod
    period_start: datetime
    period_end: datetime
    body: dict | None
    evidence_refs: list[uuid.UUID]
    status: ReportStatus
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    sent_at: datetime | None
    export_history: list
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportUpdate(BaseModel):
    """Teacher edit of a ``draft`` report's typed ``body`` sections (B5).

    Only ``body`` is editable — status transitions go through ``/approve`` /
    ``/send`` (never a raw status write), and the identity/window columns are
    fixed by the drafting job.
    """

    body: dict
