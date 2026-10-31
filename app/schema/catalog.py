from datetime import date
from typing import Any

from app.schema.common import View
from app.schema.outlook import OutlookStatus


class DepartmentView(View):
    id: int
    name: str
    senders: list[str]


class ReviewCycleView(View):
    id: str
    number: int
    send_on: date
    due_on: date
    state: str


class CarryoverCycleView(View):
    period_id: str
    send_on: date
    due_on: date


class ReviewPeriodView(View):
    id: str
    name: str
    starts: date
    ends: date
    cycles: list[ReviewCycleView]
    saturday_count: int
    monday_count: int
    carryover: CarryoverCycleView | None


class RuleView(View):
    id: int
    category: str
    settings: dict[str, Any]


class BootstrapView(View):
    mailbox: OutlookStatus
    mail_provider: str
    today: date
    timezone: str
    current_period: str
    departments: list[DepartmentView]
    periods: list[ReviewPeriodView]
    mode: str
    ocr_enabled: bool
    rules: list[RuleView]
    synthetic: bool


class DepartmentProgress(View):
    id: int
    name: str
    count: int
    received: bool


class DashboardView(View):
    total: int
    pending: int
    needs_info: int
    confirmed: int
    unknown: int
    sufficient: int
    emails: int
    email_errors: int
    departments_sent: int
    departments_expected: int
    by_department: list[DepartmentProgress]
