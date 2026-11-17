from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schema.common import IsoDateTime, View

ClockTime = Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]


class AttendanceValues(BaseModel):
    check_in: ClockTime | None = None
    check_out: ClockTime | None = None
    day_status: Literal["PRESENT", "LEAVE"] = "PRESENT"


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


class HrWorkspaceView(BaseModel):
    mode: Literal["MOCK_HR"] = "MOCK_HR"
    items: list[HrWorkspaceItem]
