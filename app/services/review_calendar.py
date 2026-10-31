"""Payroll periods run from the previous month's 26th through the named month's 25th.

The Saturday's payroll period owns the cycle. Receipt timestamps never establish a
cycle: late replies and historic monthly emails must not be silently reassigned.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = "Asia/Ho_Chi_Minh"


def business_today(now: datetime | None = None) -> date:
    if now is not None and now.tzinfo is None:
        raise ValueError("The calendar clock must include a timezone")
    return (now or datetime.now(ZoneInfo(BUSINESS_TIMEZONE))).astimezone(ZoneInfo(BUSINESS_TIMEZONE)).date()


def payroll_period(day: date) -> str:
    month = day.month + (day.day >= 26)
    year = day.year + (month > 12)
    return f"{year:04}-{(month - 1) % 12 + 1:02}"


def period_bounds(period: str) -> tuple[date, date]:
    ends = date.fromisoformat(period + "-25")
    previous_month = ends.replace(day=1) - timedelta(days=1)
    return previous_month.replace(day=26), ends


def cycle_dates(period: str) -> list[date]:
    starts, ends = period_bounds(period)
    first = starts + timedelta(days=(5 - starts.weekday()) % 7)
    return [first + timedelta(days=offset) for offset in range(0, (ends - first).days + 1, 7)]


def parse_cycle(period: str, value: str) -> date:
    candidate = date.fromisoformat(value)
    if candidate.isoformat() != value or candidate not in cycle_dates(period):
        raise ValueError("A review cycle must be a Saturday within its payroll period")
    return candidate


def default_cycle(period: str, today: date) -> date:
    cycles = cycle_dates(period)
    # Retain an open Saturday/Monday cycle, then prefer the next scheduled send.
    for send_on in cycles:
        if today <= send_on + timedelta(days=2):
            return send_on
    return cycles[-1]


def period_schedule(period: str, today: date) -> dict:
    starts, ends = period_bounds(period)
    cycles = []
    for number, send_on in enumerate(cycle_dates(period), 1):
        due_on = send_on + timedelta(days=2)
        state = (
            "UPCOMING"
            if today < send_on
            else "COLLECTING"
            if today < due_on
            else "DUE_TODAY"
            if today == due_on
            else "CLOSED"
        )
        cycles.append(
            {"id": send_on.isoformat(), "number": number, "send_on": send_on, "due_on": due_on, "state": state}
        )
    mondays = sum((starts + timedelta(days=offset)).weekday() == 0 for offset in range((ends - starts).days + 1))
    carryover = None
    if starts > date.min:
        previous_end = starts - timedelta(days=1)
        send_on = previous_end - timedelta(days=(previous_end.weekday() - 5) % 7)
        due_on = send_on + timedelta(days=2)
        if due_on >= starts:
            carryover = {"period_id": payroll_period(send_on), "send_on": send_on, "due_on": due_on}
    return {
        "id": period,
        "starts": starts,
        "ends": ends,
        "cycles": cycles,
        "saturday_count": len(cycles),
        "monday_count": mondays,
        "carryover": carryover,
    }
