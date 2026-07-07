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


class ReportShareSettings(BaseModel):
    """Export-share flags for a report (B6).

    Persisted (no migration in B6) under ``report.body['share_settings']`` and
    echoed on the export payload so an exporter knows what the recipient sees.
    ``include_evidence_appendix`` toggles whether the reviewed-notes appendix
    rides along; ``visible_to_student`` records whether the exported artefact may
    be shared with the student audience; ``allow_download`` gates a downloadable
    copy. Defaults are conservative (appendix on, student-visibility off).
    """

    include_evidence_appendix: bool = True
    visible_to_student: bool = False
    allow_download: bool = True

    model_config = {"extra": "forbid"}


class EvidenceAppendixItem(BaseModel):
    """One reviewed ``LearningNote`` resolved for the export appendix (B6).

    Only the instructor-facing reviewed fields are exposed. A note is included
    ONLY when its ``review_status ∈ {reviewed, edited}`` — an unreviewed id that
    leaked into ``evidence_refs`` is filtered out defensively (Core §0.2), so no
    unreviewed content ever reaches an export.
    """

    id: uuid.UUID
    review_status: str
    observed_signal: str
    draft_interpretation: str | None
    limitation_note: str | None

    model_config = {"from_attributes": True}


class ReportExportResponse(BaseModel):
    """The export payload returned by ``POST /reports/{id}/export`` (B6).

    ``evidence_appendix`` resolves ``evidence_refs`` → reviewed notes ONLY (an
    unreviewed id is filtered out). ``share_settings`` echoes the report's stored
    flags. ``exported_at`` matches the ``export_history`` entry just appended.
    """

    report: ReportResponse
    evidence_appendix: list[EvidenceAppendixItem]
    share_settings: ReportShareSettings
    exported_at: datetime


class ReportShareSettingsResponse(BaseModel):
    """Returned by ``PATCH /reports/{id}/share-settings`` — the persisted flags."""

    report_id: uuid.UUID
    share_settings: ReportShareSettings
