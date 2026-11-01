from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.schema.common import IsoDateTime, View

ClockTime = Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]


class AttendanceValues(BaseModel):
    check_in: ClockTime | None = None
    check_out: ClockTime | None = None
    day_status: Literal["PRESENT", "LEAVE"] = "PRESENT"


class CorrectionValues(AttendanceValues):
    @model_validator(mode="after")
    def complete_same_day_correction(self):
        if self.day_status == "LEAVE":
            if self.check_in is not None or self.check_out is not None:
                raise ValueError("Ngày nghỉ phải để trống giờ vào và giờ ra.")
        elif not self.check_in or not self.check_out or self.check_in >= self.check_out:
            raise ValueError("Nhập giờ vào và giờ ra hợp lệ trong cùng ngày; giờ ra phải sau giờ vào.")
        return self


class HrSubmitRequest(CorrectionValues):
    version_id: int = Field(gt=0)
    review_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_revision: int = Field(gt=0)
    reason: str = Field(min_length=10, max_length=1000)
    acknowledged: bool


class HrSubmissionView(View):
    id: str
    case_id: int
    version_id: int
    target: str
    status: str
    requested_by: str
    payload: dict
    receipt: dict
    error: str | None
    created_at: IsoDateTime
    applied_at: IsoDateTime | None


class MockSeedRecord(AttendanceValues):
    id: str = Field(pattern=r"^[a-f0-9]{64}$")
    source: Literal["mailpit", "outlook"]
    employee_id: str = Field(min_length=1, max_length=60)
    employee_name: str = Field(max_length=200)
    department: str = Field(max_length=200)
    work_date: date
    shift: str = Field(min_length=1, max_length=200)


class MockSeedRequest(BaseModel):
    records: list[MockSeedRecord] = Field(max_length=200)


class MockLookupRequest(BaseModel):
    ids: list[str] = Field(max_length=200)


class MockApplyRequest(CorrectionValues):
    expected_revision: int = Field(gt=0)
    reason: str = Field(min_length=10, max_length=1000)
    case_code: str = Field(min_length=1, max_length=60)
    version_id: int = Field(gt=0)
    requested_by: str = Field(min_length=1, max_length=80)


class MockAttendanceView(View, AttendanceValues):
    id: str
    source: str
    employee_id: str
    employee_name: str
    department: str
    work_date: date
    shift: str
    revision: int
    updated_at: IsoDateTime


class MockReceiptView(View):
    id: str
    record_id: str
    before: dict
    after: dict
    source: dict
    created_at: IsoDateTime


class HrCaseView(BaseModel):
    mode: Literal["MOCK_HR"] = "MOCK_HR"
    record: MockAttendanceView | None
    suggested: AttendanceValues
    suggestion_source: str
    suggested_reason: str
    review_token: str
    version_id: int
    can_submit: bool
    blocked_reason: str | None
    submissions: list[HrSubmissionView]


class HrWorkspaceItem(BaseModel):
    case_id: int
    case_code: str
    employee_id: str
    employee_name: str
    department: str
    work_date: str
    shift: str
    hr_status: str
    record: MockAttendanceView | None
    submission: HrSubmissionView | None


class HrWorkspaceView(BaseModel):
    mode: Literal["MOCK_HR"] = "MOCK_HR"
    connected: bool
    error: str | None = None
    items: list[HrWorkspaceItem]
