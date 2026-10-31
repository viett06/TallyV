from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.i18n import message
from app.core.serialization import model_dict as record
from app.crud import cases as case_crud
from app.crud import catalog as catalog_crud
from app.crud import emails as email_crud
from app.models import ReviewPeriod
from app.schema.cases import CaseFilters
from app.services.cases import eligible
from app.services.mailbox_auth import connection_status
from app.services.review_calendar import (
    BUSINESS_TIMEZONE,
    business_today,
    payroll_period,
    period_bounds,
    period_schedule,
)


def ensure_period(db: Session, period_id: str) -> ReviewPeriod:
    starts, ends = period_bounds(period_id)
    period = catalog_crud.get_period(db, period_id)
    if period is None:
        period = ReviewPeriod(
            id=period_id,
            name=message("calendar.month_name", month=ends.month, year=ends.year),
            starts=starts,
            ends=ends,
        )
        db.add(period)
        db.flush()
    elif period.starts != starts or period.ends != ends:
        period.starts, period.ends = starts, ends
    return period


def active_departments(db: Session):
    return [
        department
        for department in catalog_crud.list_departments(db)
        if settings.mail_provider == "mailpit"
        or not department.senders
        or any(not sender.endswith("@demo.invalid") for sender in department.senders)
    ]


def bootstrap(db: Session) -> dict:
    today = business_today()
    current_period = payroll_period(today)
    year = int(current_period[:4])
    period_ids = (
        {p.id for p in catalog_crud.list_periods(db)}
        | {f"{year:04}-{month:02}" for month in range(1, 13)}
        | {f"{year - 1:04}-12"}
    )
    periods = []
    for period_id in sorted(period_ids, reverse=True):
        schedule = period_schedule(period_id, today)
        schedule["name"] = message("calendar.month_name", month=schedule["ends"].month, year=schedule["ends"].year)
        periods.append(schedule)
    return {
        "mailbox": connection_status(db),
        "mail_provider": settings.mail_provider,
        "today": today,
        "timezone": BUSINESS_TIMEZONE,
        "current_period": current_period,
        "departments": [{**record(x), "senders": x.senders} for x in active_departments(db)],
        "periods": periods,
        "mode": settings.processing_mode,
        "ocr_enabled": settings.ocr_enabled,
        "rules": [record(x) for x in catalog_crud.list_rules(db)],
        "synthetic": settings.mail_provider == "mailpit",
    }


def dashboard(db: Session, selection: CaseFilters) -> dict:
    rows = case_crud.list_rows(db, selection)
    emails = email_crud.list_emails(db, selection.period, selection.department, selection.cycle, selection.source)
    departments = active_departments(db)
    counts = {d.id: 0 for d in departments}
    for case, *_ in rows:
        counts[case.department_id] = counts.get(case.department_id, 0) + 1
    return {
        "total": len(rows),
        "pending": sum(c.hr_status == "PENDING_REVIEW" for c, *_ in rows),
        "needs_info": sum(c.hr_status == "NEEDS_INFO" for c, *_ in rows),
        "confirmed": sum(c.hr_status == "CONFIRMED" for c, *_ in rows),
        "unknown": sum(a.status == "COMPLETED" and a.category == "UNKNOWN" for _, _, a, *_ in rows),
        "sufficient": sum(eligible(db, c, a) for c, _, a, *_ in rows),
        "emails": len(emails),
        "email_errors": sum(e.status in {"PARTIAL_ERROR", "FAILED", "NEEDS_REVIEW"} for e in emails),
        "departments_sent": len({e.department_id for e in emails if e.department_id}),
        "departments_expected": len(departments),
        "by_department": [
            {
                "id": d.id,
                "name": d.name,
                "count": counts[d.id],
                "received": any(e.department_id == d.id for e in emails),
            }
            for d in departments
        ],
    }
