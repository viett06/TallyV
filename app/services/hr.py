"""Read and seed the reference attendance table from the application database."""

import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.attendance import HR_DEMO_SHIFTS, PUNCH_IN, PUNCH_OUT
from app.core.config import settings
from app.core.errors import AppError
from app.core.i18n import message
from app.crud import cases as case_store
from app.models import AuditLog, MockHrAttendance, User
from app.schema.cases import CaseFilters
from app.schema.hr import MockSeedRecord


def _source(case, email) -> str:
    if case.manual_source:
        return case.manual_source
    return "outlook" if email.source_id.startswith("outlook:") else "mailpit"


def _record_id(case, version, email) -> str:
    identity = [_source(case, email), case.employee_id, version.normalized["date"], version.normalized["shift"]]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def _schedule(shift: str) -> tuple[str | None, str | None]:
    # Explicit ranges in the source label, or our two documented synthetic shifts.
    match = re.search(r"(?<!\d)([0-2]\d:[0-5]\d)\s*[–—-]\s*([0-2]\d:[0-5]\d)(?!\d)", shift)
    if match and match[1] < match[2] and match[1] < "24:00" and match[2] < "24:00":
        return match[1], match[2]
    if shift in HR_DEMO_SHIFTS:
        return HR_DEMO_SHIFTS[shift]["check_in"], HR_DEMO_SHIFTS[shift]["check_out"]
    return None, None


def _scope_rows(db: Session, selection: CaseFilters):
    rows = case_store.list_rows(db, selection, ordered=True)
    if len(rows) > 200:
        raise AppError(422, message("hr.scope_too_large"))
    return rows


def workspace(db: Session, selection: CaseFilters) -> dict:
    rows = _scope_rows(db, selection)
    record_ids = [_record_id(case, version, email) for case, version, _, _, email in rows]
    records = {row.id: row for row in db.scalars(select(MockHrAttendance).where(MockHrAttendance.id.in_(record_ids)))}
    return {
        "items": [
            {
                "case_id": case.id,
                "case_code": case.code,
                "employee_id": case.employee_id,
                "employee_name": version.normalized["name"],
                "department": department.name,
                "work_date": version.normalized["date"],
                "shift": version.normalized["shift"],
                "hr_status": case.hr_status,
                "record": records.get(record_id),
            }
            for (case, version, _, department, _), record_id in zip(rows, record_ids, strict=True)
        ],
    }


def seed(db: Session, selection: CaseFilters, user: User) -> dict:
    if settings.mail_provider == "outlook" and not settings.outlook_test_mode:
        raise AppError(409, message("hr.synthetic_only"))
    records: dict[str, MockSeedRecord] = {}
    for case, version, _, department, email in _scope_rows(db, selection):
        data = version.normalized
        if not data["shift"]:
            continue
        start, end = _schedule(data["shift"])
        record_id = _record_id(case, version, email)
        records[record_id] = MockSeedRecord(
            id=record_id,
            source=_source(case, email),
            employee_id=case.employee_id,
            employee_name=data["name"],
            department=department.name,
            work_date=data["date"],
            shift=data["shift"],
            check_in=None if data["punch"] == PUNCH_IN else start,
            check_out=None if data["punch"] == PUNCH_OUT else end,
        )
    created = 0
    for record_id in sorted(records):
        if db.get(MockHrAttendance, record_id):
            continue
        try:
            with db.begin_nested():
                db.add(MockHrAttendance(**records[record_id].model_dump()))
        except IntegrityError:
            if db.get(MockHrAttendance, record_id) is None:
                raise
        else:
            created += 1
    result = {"created": created}
    db.add(AuditLog(actor=user.username, action="HR_DEMO_SEEDED", after=result, reason=message("hr.seed_audit")))
    db.commit()
    return result
