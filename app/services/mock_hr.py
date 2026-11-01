"""Small HR simulator: persistent time records, optimistic locking, durable receipts."""

import hashlib
import json

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.i18n import message
from app.core.serialization import model_dict
from app.core.time import utcnow
from app.crud import mock_hr as store
from app.models import MockHrAttendance, MockHrReceipt
from app.schema.hr import MockApplyRequest, MockAttendanceView, MockSeedRequest


def seed(db: Session, body: MockSeedRequest) -> dict:
    created = 0
    for source in sorted(body.records, key=lambda r: r.id):
        if store.get_record(db, source.id):
            continue
        record = MockHrAttendance(**source.model_dump())
        db.add(record)
        db.flush()
        created += 1
    db.commit()
    return {"created": created}


def apply(db: Session, record_id: str, request_id: str, body: MockApplyRequest) -> dict:
    # Serialize changes to the target record, including receipt replay checks.
    record = store.get_record(db, record_id, for_update=True)
    if not record:
        raise AppError(404, message("hr.target_record_missing"))
    digest = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    receipt = store.get_receipt(db, request_id)
    if receipt:
        if receipt.record_id != record_id or receipt.request_hash != digest:
            raise AppError(409, message("hr.idempotency_conflict"))
        return model_dict(receipt)
    if record.revision != body.expected_revision:
        raise AppError(409, message("hr.target_conflict"))
    before = MockAttendanceView.model_validate(record).model_dump(mode="json")
    record.check_in, record.check_out, record.day_status = body.check_in, body.check_out, body.day_status
    record.revision += 1
    record.updated_at = utcnow()
    receipt = MockHrReceipt(
        id=request_id,
        record_id=record_id,
        request_hash=digest,
        before=before,
        after=MockAttendanceView.model_validate(record).model_dump(mode="json"),
        source={
            "case_code": body.case_code,
            "version_id": body.version_id,
            "requested_by": body.requested_by,
            "reason": body.reason,
        },
    )
    db.add(receipt)
    db.commit()
    return model_dict(receipt)
