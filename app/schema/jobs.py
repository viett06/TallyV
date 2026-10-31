from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schema.common import IsoDateTime, JobQueued, View


class JobView(View):
    id: int
    kind: str
    key: str
    payload: dict[str, Any]
    status: str
    attempts: int
    max_attempts: int
    available_at: IsoDateTime
    locked_at: IsoDateTime | None
    error: str | None


class SyncQueued(JobQueued):
    status: str


class AnalysisStatus(BaseModel):
    waiting: int
    processing: int
    completed: int
    failed: int
    importing: bool


class AnalysisQueued(BaseModel):
    queued: int


class MailboxScanRequest(BaseModel):
    mode: Literal["incremental", "rescan"] = "incremental"
    lookback_days: int = Field(default=90, ge=1, le=365)


class DemoQueued(JobQueued):
    message: str


class DemoRequest(BaseModel):
    period: str = Field(default="", pattern=r"^(?:|\d{4}-\d{2})$")
    cycle: date | None = None
