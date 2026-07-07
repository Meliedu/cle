"""Attendance / QR-launch schemas (P3 T9+)."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class LaunchRequest(BaseModel):
    """Body for ``POST /checkpoints/{id}/launch``.

    ``rotate`` closes the prior active launch and issues a fresh token; the
    default (first launch) creates the single active launch.
    """

    rotate: bool = False


class LaunchResponse(BaseModel):
    """A minted (or rotated) QR launch — the signed ``token`` is rendered as a
    QR by the teacher panel (T045); ``window_end`` drives the countdown."""

    id: uuid.UUID
    checkpoint_id: uuid.UUID
    meeting_id: uuid.UUID
    token: str
    jti: str
    window_start: datetime
    window_end: datetime
    status: str

    model_config = {"from_attributes": True}
