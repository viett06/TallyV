from datetime import date
from typing import Any

from app.schema.common import IsoDateTime, View


class AttachmentView(View):
    id: int
    email_id: int
    part_index: int
    name: str
    sha256: str
    size: int
    status: str
    error: str | None
    duplicate_of: int | None


class EmailView(View):
    id: int
    source_id: str
    message_id: str | None
    sender: str
    recipient: str
    subject: str
    body: str
    received_at: IsoDateTime
    ingested_at: IsoDateTime
    department_id: int | None
    period_id: str | None
    cycle_start: date | None
    status: str
    error: str | None
    row_count: int
    error_count: int
    attachments: list[AttachmentView]


class EmailListItem(EmailView):
    case_count: int
    department: str


class ImportBatchView(View):
    id: int
    attachment_id: int
    sheet: str
    row_count: int
    imported_count: int
    duplicate_count: int
    error_count: int
    errors: list[dict[str, Any]]


class EmailCaseReference(View):
    id: int
    code: str
    row: int
    version_status: str


class EmailDetailView(EmailView):
    batches: list[ImportBatchView]
    cases: list[EmailCaseReference]
