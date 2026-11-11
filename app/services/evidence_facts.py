"""Structured OCR observations and deterministic attendance comparisons."""

import re
import unicodedata
from datetime import date

from app.core.attendance import HR_DEMO_SHIFTS, PUNCH_IN, PUNCH_OUT
from app.core.config import settings

CLOCK = r"(?:[01]?\d|2[0-3]):[0-5]\d"
TIME = re.compile(rf"(?<!\d){CLOCK}(?::[0-5]\d)?(?!\d)")
DEVICE_ID = re.compile(r"\b(?:ma may|ma thiet bi|device id|terminal id)\s*[:#]\s*([a-z0-9_-]{1,40})\b")
CAMERA_ID = re.compile(r"\b(?:ma camera|camera id|camera)\s*[:#]\s*([a-z0-9_-]{1,40})\b")
UNRELATED_TIME = re.compile(r"\b(?:gio hien tai|ngay xuat|xuat bao cao|generated at|exported at|current time)\b")
EVENT_TIME = re.compile(r"\b(?:gio quet|gio cham cong|gio vao|gio ra|thoi diem|event time|scan time)\s*[:=]")
SCAN_STATES = {
    "DEVICE_ERROR": r"\b(?:device error|loi thiet bi|loi he thong|mat ket noi|offline|timeout|disconnected)\b",
    "NOT_RECORDED": r"\b(?:not recorded|chua ghi nhan|khong ghi nhan)\b",
    "RECORDED": r"\b(?:recorded|da ghi nhan|cham cong thanh cong)\b",
    "RECOGNIZED": r"\b(?:recognized|nhan dien thanh cong)\b",
    "FAILED": r"\b(?:failed|that bai|khong nhan dien)\b",
}


def minute(clock: str) -> int:
    hour, minute_value, *_ = map(int, clock.split(":"))
    return hour * 60 + minute_value


def shift_interval(shift: str) -> tuple[int, int] | None:
    intervals = re.findall(rf"(?<!\d)({CLOCK})\s*[-–—]\s*({CLOCK})(?!\d)", shift)
    if len(intervals) == 1:
        start, end = map(minute, intervals[0])
    elif settings.mail_provider == "mailpit" and shift in HR_DEMO_SHIFTS:
        demo = HR_DEMO_SHIFTS[shift]
        start, end = minute(demo["check_in"]), minute(demo["check_out"])
    else:
        return None
    return (start, end + (1440 if end < start else 0)) if start != end else None


def _canonical(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().upper()


def add_ocr_facts(extracted: dict, text: str, plain_text: str) -> None:
    for field, pattern in (("device_id", DEVICE_ID), ("camera_id", CAMERA_ID)):
        observed = set(pattern.findall(plain_text))
        if len(observed) == 1:
            extracted[field] = next(iter(observed)).upper()
    positive_text = re.sub(r"\b(?:not recorded|not recognized|khong mat ket noi)\b", "", plain_text)
    statuses = [
        state
        for state, pattern in SCAN_STATES.items()
        if re.search(pattern, plain_text if state == "NOT_RECORDED" else positive_text)
    ]
    if statuses:
        extracted["observed_states"] = statuses
    times = set(TIME.findall(text))
    lines = [line for line in plain_text.splitlines() if EVENT_TIME.search(line)]
    labeled = {time for line in lines for time in TIME.findall(line[EVENT_TIME.search(line).end() :])}
    if len(labeled) == 1:
        extracted["time"] = next(iter(labeled))
        extracted["time_source"] = "LABELED_EVENT"
    elif len(times) == 1 and not any(
        TIME.search(line) and UNRELATED_TIME.search(line) for line in plain_text.splitlines()
    ):
        extracted["time"] = next(iter(times))
        extracted["time_source"] = "ONLY_VISIBLE_TIME"
    elif times:
        extracted.pop("time", None)
        extracted["time_source"] = "AMBIGUOUS"
    else:
        extracted["time_source"] = "NOT_VISIBLE"
    extracted["time_observation_source"] = "OCR"


def compare(extracted: dict, data: dict) -> dict:
    observed_employee = extracted.get("employee_id")
    employee = data.get("employee_id")
    observed_date = extracted.get("date")
    work_date = data.get("date")
    clock = extracted.get("time")
    interval = shift_interval(data.get("shift", ""))
    day_delta = (
        (date.fromisoformat(observed_date) - date.fromisoformat(work_date)).days
        if observed_date and work_date
        else None
    )
    clock_index = day_delta * 1440 + minute(clock) if day_delta is not None and clock else None
    in_shift = interval[0] <= clock_index <= interval[1] if interval and clock_index is not None else None
    overnight = interval and interval[1] >= 1440
    date_match = day_delta == 0 if day_delta is not None else None
    if day_delta == 1 and overnight:
        date_match = in_shift
    punch = data.get("punch")
    offset = None
    if interval and clock_index is not None and day_delta in (0, 1) and punch in {PUNCH_IN, PUNCH_OUT}:
        if day_delta == 0 or overnight:
            expected = interval[0] if punch == PUNCH_IN else interval[1]
            offset = clock_index - expected
    return {
        "employee_match": _match(
            _canonical(employee) == _canonical(observed_employee) if employee and observed_employee else None
        ),
        "work_date_match": _match(date_match),
        "shift_match": _match(in_shift),
        "minutes_from_expected_punch": offset,
        "punch": "IN" if punch == PUNCH_IN else "OUT" if punch == PUNCH_OUT else None,
    }


def _match(value: bool | None) -> str:
    if value is None:
        return "UNKNOWN"
    return "MATCH" if value else "MISMATCH"
