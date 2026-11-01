from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MockHrAttendance, MockHrReceipt


def get_record(db: Session, record_id: str, *, for_update: bool = False) -> MockHrAttendance | None:
    query = select(MockHrAttendance).where(MockHrAttendance.id == record_id)
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def list_records(db: Session, ids: list[str]) -> list[MockHrAttendance]:
    return list(db.scalars(select(MockHrAttendance).where(MockHrAttendance.id.in_(ids))))


def get_receipt(db: Session, request_id: str) -> MockHrReceipt | None:
    return db.get(MockHrReceipt, request_id)
