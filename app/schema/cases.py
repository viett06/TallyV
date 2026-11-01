from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
from app.schema.common import IsoDateTime, View
from app.schema.hr import HrSubmissionView

CycleFilter = date | Literal["", "unassigned"]


class CaseFilters(BaseModel):
    source: Literal["", "mailpit", "outlook", "all"] = ""
    period: str = ""
    cycle: CycleFilter = ""
    department: str = ""
    search: str = ""
    category: str = ""
    assessment: str = ""
    hr_status: str = ""

    @model_validator(mode="after")
    def default_to_configured_source(self):
        if not self.source:
            self.source = settings.mail_provider
        return self


class CaseReviewRequest(BaseModel):
    category: Literal["FORGOT_CHECK", "DEVICE_ERROR", "LEAVE_NOT_RECORDED", "UNKNOWN"]
    status: Literal["PENDING_REVIEW", "NEEDS_INFO", "CONFIRMED"]
    note: str = Field(default="", max_length=2000)
    acknowledge_exception: bool = False
    override_reason: str = Field(default="", max_length=1000)


class BulkConfirmRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)
    acknowledged: bool


class VersionDecisionRequest(BaseModel):
    action: Literal["APPLY", "REJECT"]
    reason: str = Field(min_length=5, max_length=1000)


class AnalysisView(View):
    id: int
    version_id: int
    status: str
    category: str
    reason: str
    extracted: dict[str, Any]
    missing: list[str]
    conflicts: list[str]
    evidence_checks: list[dict[str, Any]]
    assessment: str
    method: str
    rules_version: str
    model: str | None
    error: str | None


class SourceView(BaseModel):
    email_id: int
    subject: str
    sender: str
    attachment_id: int
    sheet: str
    row: int


class CaseView(View):
    id: int
    code: str
    employee_id: str
    department_id: int
    period_id: str
    cycle_start: date | None
    active_version_id: int | None
    hr_status: str
    hr_category: str | None
    hr_note: str
    confirmed_by: str | None
    confirmed_at: IsoDateTime | None
    created_at: IsoDateTime
    data: dict[str, str]
    analysis: AnalysisView
    department: str
    source: SourceView
    evidence_count: int
    bulk_eligible: bool
    proposed_count: int
    hr_submission: HrSubmissionView | None = None


class CaseListView(BaseModel):
    items: list[CaseView]
    total: int
    page: int
    page_size: int


class EvidenceView(View):
    id: int
    version_id: int
    sha256: str
    anchor: str
    ocr_status: str
    ocr_text: str
    extracted: dict[str, Any]
    checks: list[str]
    url: str


class CaseVersionView(View):
    id: int
    case_id: int
    attachment_id: int
    sheet: str
    row_number: int
    fingerprint: str
    raw: dict[str, str]
    normalized: dict[str, str]
    issues: list[str]
    status: str
    created_at: IsoDateTime
    evidence: list[EvidenceView]
    analysis: AnalysisView | None


class AuditView(View):
    id: int
    case_id: int | None
    actor: str
    action: str
    before: dict[str, Any]
    after: dict[str, Any]
    reason: str
    created_at: IsoDateTime


class CaseDetailView(CaseView):
    versions: list[CaseVersionView]
    audit: list[AuditView]


class BulkResult(BaseModel):
    confirmed: int
