from pydantic import BaseModel


class RecalibrationContentTypeSummary(BaseModel):
    content_type: str
    items_scanned: int
    items_relabeled: int
    relabel_pct: float
    last_run: str | None


class RecalibrationOverviewResponse(BaseModel):
    summaries: list[RecalibrationContentTypeSummary]
    transition_matrices: dict[str, dict[str, dict[str, float]]]


class RecalibrationItemRow(BaseModel):
    pool_item_id: str
    content_type: str
    item_preview: str
    llm_difficulty: str
    recalibrated_difficulty: str | None
    confidence: float | None
    attempt_count: int
    correct_rate: float
    instructor_override: bool


class RecalibrationItemsResponse(BaseModel):
    items: list[RecalibrationItemRow]
    total: int
    page: int
    limit: int
    pages: int
