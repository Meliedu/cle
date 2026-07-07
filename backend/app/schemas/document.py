import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    uploaded_by: uuid.UUID
    filename: str
    file_type: str
    file_size: int | None
    status: str
    page_count: int | None
    word_count: int | None
    meeting_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentAssignRequest(BaseModel):
    """Assign a document to a session (``meeting_id``) or unassign it (``null``).

    The only mutable field on the materials PATCH; an explicit ``null`` unassigns.
    """

    meeting_id: uuid.UUID | None = None


class MaterialGroup(BaseModel):
    """One session folder: the meeting + the documents assigned to it (Decision 6)."""

    meeting_id: uuid.UUID
    meeting_index: int
    title: str | None
    release_state: str
    documents: list[DocumentResponse]


class MaterialsLibrary(BaseModel):
    """The course materials library grouped into session folders.

    ``sessions`` are the per-meeting folders; ``unassigned`` holds documents with
    no ``meeting_id`` (owner view only — students never see the unassigned bucket
    nor non-released sessions).
    """

    sessions: list[MaterialGroup]
    unassigned: list[DocumentResponse]


class MaterialPreview(BaseModel):
    """A short-lived signed R2 URL for previewing a document (never raw bytes)."""

    url: str
    expires_in: int
    filename: str
    file_type: str
