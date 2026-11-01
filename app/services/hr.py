"""HR-reviewed corrections. The worker sends immutable requests to an HTTP adapter."""

import hashlib
import json
import re

from sqlalchemy.orm import Session

from app.core.attendance import HR_DEMO_SHIFTS, PUNCH_IN, PUNCH_OUT
from app.core.config import settings
from app.core.errors import AppError
from app.core.i18n import message
from app.core.serialization import json_value, model_dict
from app.core.time import utcnow
from app.crud import cases as case_store
from app.crud import hr as store
from app.crud import jobs as job_store
from app.models import AuditLog, HrSubmission, User
from app.schema.cases import CaseFilters
from app.schema.hr import HrSubmitRequest, MockApplyRequest, MockSeedRecord
from app.services.hr_connector import connector


def _source(email) -> str:
    return "outlook" if email.source_id.startswith("outlook:") else "mailpit"


def _record_id(case, version, email) -> str:
    identity = [_source(email), case.employee_id, version.normalized["date"], version.normalized["shift"]]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def _review_token(case, version, analysis) -> str:
    snapshot = {
        "case": {k: json_value(getattr(case, k)) for k in ("hr_status", "hr_category", "hr_note", "confirmed_at")},
        "version": version.fingerprint,
        "analysis": {k: getattr(analysis, k) for k in ("status", "category", "assessment", "rules_version")},
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _blocked(db: Session, case, analysis) -> str | None:
    if settings.mail_provider == "outlook" and not settings.outlook_test_mode:
        return message("hr.synthetic_only")
    if case_store.proposed_count(db, case.id):
        return message("review.version_decision_required")
    if not analysis or analysis.status != "COMPLETED":
        return message("hr.analysis_required")
    if (
        case.hr_status != "CONFIRMED"
        or not case.confirmed_by
        or not case.confirmed_at
        or case.hr_category not in {"FORGOT_CHECK", "DEVICE_ERROR", "LEAVE_NOT_RECORDED"}
    ):
        return message("hr.confirmation_required")
    return None


def _row(db: Session, case_id: int, *, locked: bool = False):
    if locked and not case_store.get_for_update(db, case_id):
        raise AppError(404, message("cases.not_found"))
    row = case_store.get_row(db, case_id)
    if not row:
        raise AppError(404, message("cases.not_found"))
    return row


def _schedule(shift: str) -> tuple[str | None, str | None]:
    # Explicit ranges in the source label, or our two documented synthetic shifts.
    match = re.search(r"(?<!\d)([0-2]\d:[0-5]\d)\s*[–—-]\s*([0-2]\d:[0-5]\d)(?!\d)", shift)
    if match and match[1] < match[2] and match[1] < "24:00" and match[2] < "24:00":
        return match[1], match[2]
    if shift in HR_DEMO_SHIFTS:
        return HR_DEMO_SHIFTS[shift]["check_in"], HR_DEMO_SHIFTS[shift]["check_out"]
    return None, None


def _suggest(case, version, current: dict | None) -> dict:
    if case.hr_category == "LEAVE_NOT_RECORDED":
        return {"check_in": None, "check_out": None, "day_status": "LEAVE"}
    start, end = _schedule(version.normalized["shift"])
    return {
        "check_in": (current or {}).get("check_in") or start,
        "check_out": (current or {}).get("check_out") or end,
        "day_status": "PRESENT",
    }


def case_preview(db: Session, case_id: int) -> dict:
    case, version, analysis, _, email = _row(db, case_id)
    record_id = _record_id(case, version, email)
    current = connector.lookup([record_id]).get(record_id)
    reason = _blocked(db, case, analysis)
    if not current:
        reason = reason or message("hr.seed_required")
    return {
        "record": current,
        "suggested": _suggest(case, version, current),
        "suggestion_source": message("hr.suggestion_source"),
        "suggested_reason": case.hr_note or version.normalized["explanation"],
        "review_token": _review_token(case, version, analysis),
        "version_id": version.id,
        "can_submit": reason is None,
        "blocked_reason": reason,
        "submissions": [model_dict(s) for s in store.list_submissions(db, case.id)],
    }


def _scope_rows(db: Session, selection: CaseFilters):
    rows = case_store.list_rows(db, selection, ordered=True)
    if len(rows) > 200:
        raise AppError(422, message("hr.scope_too_large"))
    return rows


def workspace(db: Session, selection: CaseFilters) -> dict:
    rows = _scope_rows(db, selection)
    connected, error, records = True, None, {}
    try:
        # Health is checked even before any cases exist.
        connector.health()
        records = connector.lookup([_record_id(c, v, e) for c, v, _, _, e in rows])
    except AppError as exc:
        connected, error = False, exc.detail
    return {
        "connected": connected,
        "error": error,
        "items": [
            {
                "case_id": c.id,
                "case_code": c.code,
                "employee_id": c.employee_id,
                "employee_name": v.normalized["name"],
                "department": d.name,
                "work_date": v.normalized["date"],
                "shift": v.normalized["shift"],
                "hr_status": c.hr_status,
                "record": records.get(_record_id(c, v, e)),
                "submission": model_dict(store.latest_submission(db, c.id)),
            }
            for c, v, _, d, e in rows
        ],
    }


def seed(db: Session, selection: CaseFilters, user: User) -> dict:
    if settings.mail_provider == "outlook" and not settings.outlook_test_mode:
        raise AppError(409, message("hr.synthetic_only"))
    records = {}
    for case, version, _, department, email in _scope_rows(db, selection):
        data = version.normalized
        if not data["shift"]:
            continue
        start, end = _schedule(data["shift"])
        record_id = _record_id(case, version, email)
        records[record_id] = MockSeedRecord(
            id=record_id,
            source=_source(email),
            employee_id=case.employee_id,
            employee_name=data["name"],
            department=department.name,
            work_date=data["date"],
            shift=data["shift"],
            check_in=None if data["punch"] == PUNCH_IN else start,
            check_out=None if data["punch"] == PUNCH_OUT else end,
        ).model_dump(mode="json")
    result = connector.seed(list(records.values()))
    db.add(AuditLog(actor=user.username, action="HR_DEMO_SEEDED", after=result, reason=message("hr.seed_audit")))
    db.commit()
    return result


def submit(db: Session, case_id: int, body: HrSubmitRequest, user: User) -> dict:
    case, version, analysis, _, email = _row(db, case_id, locked=True)
    reason = _blocked(db, case, analysis)
    if reason:
        raise AppError(409, reason)
    if body.version_id != version.id or body.review_token != _review_token(case, version, analysis):
        raise AppError(409, message("hr.review_changed"))
    if not body.acknowledged or len(body.reason.strip()) < 10:
        raise AppError(422, message("hr.acknowledgement_required"))
    if (body.day_status == "LEAVE") != (case.hr_category == "LEAVE_NOT_RECORDED"):
        raise AppError(422, message("hr.correction_type_mismatch"))
    payload = MockApplyRequest(
        **body.model_dump(include={"check_in", "check_out", "day_status", "expected_revision"}),
        reason=body.reason.strip(),
        case_code=case.code,
        version_id=version.id,
        requested_by=user.username,
    ).model_dump(mode="json")
    for previous in store.list_submissions(db, case.id):
        if previous.status == "QUEUED" or (previous.status == "APPLIED" and previous.version_id == version.id):
            if previous.payload["correction"] != payload and previous.status == "QUEUED":
                raise AppError(409, message("hr.already_queued"))
            return model_dict(previous)
    record_id = _record_id(case, version, email)
    current = connector.lookup([record_id]).get(record_id)
    if not current:
        raise AppError(409, message("hr.seed_required"))
    if current["revision"] != body.expected_revision:
        raise AppError(409, message("hr.target_conflict"))
    if all(current[k] == payload[k] for k in ("check_in", "check_out", "day_status")):
        raise AppError(422, message("hr.no_change"))
    submission = HrSubmission(
        case_id=case.id,
        version_id=version.id,
        requested_by=user.username,
        review_token=body.review_token,
        payload={"record_id": record_id, "correction": payload},
    )
    db.add(submission)
    db.flush()
    job_store.enqueue(db, "HR_SUBMIT", "hr-submit:" + submission.id, {"submission_id": submission.id})
    db.add(
        AuditLog(
            case_id=case.id,
            actor=user.username,
            action="HR_SUBMISSION_REQUESTED",
            before={"record": current},
            after={"submission_id": submission.id, "correction": payload},
            reason=body.reason.strip(),
        )
    )
    db.commit()
    return model_dict(submission)


def _mark_applied(db: Session, submission: HrSubmission, receipt: dict):
    expected = submission.payload["correction"]
    if (
        receipt["id"] != submission.id
        or receipt["record_id"] != submission.payload["record_id"]
        or any(receipt["after"].get(k) != expected[k] for k in ("check_in", "check_out", "day_status"))
    ):
        raise AppError(502, message("hr.invalid_response"))
    submission.status, submission.receipt, submission.error = "APPLIED", receipt, None
    submission.applied_at = utcnow()
    db.add(
        AuditLog(
            case_id=submission.case_id,
            actor=submission.requested_by,
            action="HR_SUBMISSION_APPLIED",
            before=receipt["before"],
            after={"submission_id": submission.id, "record": receipt["after"]},
            reason=expected["reason"],
        )
    )


def process_submission(db: Session, submission_id: str):
    submission = store.get_submission(db, submission_id)
    if not submission or submission.status != "QUEUED":
        return
    case, version, analysis, *_ = _row(db, submission.case_id, locked=True)
    submission = store.get_submission(db, submission_id, refresh=True)
    if submission.status != "QUEUED":
        return
    # Recover an accepted request after a lost response or local transaction rollback.
    receipt = connector.receipt(submission.id)
    if receipt is not None:
        _mark_applied(db, submission, receipt)
        return
    reason = _blocked(db, case, analysis)
    if (
        reason
        or submission.version_id != version.id
        or submission.review_token != _review_token(case, version, analysis)
    ):
        submission.status, submission.error = "CANCELLED", reason or message("hr.review_changed")
        db.add(
            AuditLog(
                case_id=case.id,
                actor="system",
                action="HR_SUBMISSION_CANCELLED",
                after={"submission_id": submission.id},
                reason=submission.error,
            )
        )
        return
    try:
        receipt = connector.apply(submission.id, submission.payload["record_id"], submission.payload["correction"])
    except AppError as error:
        if error.status_code != 409:
            raise
        submission.status, submission.error = "FAILED", error.detail
        db.add(
            AuditLog(
                case_id=case.id,
                actor="system",
                action="HR_SUBMISSION_FAILED",
                after={"submission_id": submission.id},
                reason=error.detail,
            )
        )
        return
    _mark_applied(db, submission, receipt)


def retry(db: Session, submission_id: str, user: User) -> dict:
    submission = store.get_submission(db, submission_id)
    if not submission or submission.status != "FAILED":
        raise AppError(409, message("hr.retry_requires_failure"))
    case, version, analysis, *_ = _row(db, submission.case_id, locked=True)
    submission = store.get_submission(db, submission_id, refresh=True)
    if submission.status != "FAILED":
        raise AppError(409, message("hr.retry_requires_failure"))
    receipt = connector.receipt(submission.id)
    if receipt is not None:
        _mark_applied(db, submission, receipt)
        job = job_store.get_by_key(db, "hr-submit:" + submission.id)
        if job:
            job.status, job.error, job.locked_at = "DONE", None, None
        db.commit()
        return model_dict(submission)
    if (
        _blocked(db, case, analysis)
        or submission.version_id != version.id
        or submission.review_token != _review_token(case, version, analysis)
    ):
        raise AppError(409, message("hr.review_changed"))
    others = store.list_submissions(db, case.id)
    if any(s.id != submission.id and s.status in {"QUEUED", "APPLIED"} and s.version_id == version.id for s in others):
        raise AppError(409, message("hr.already_queued"))
    submission.status, submission.error = "QUEUED", None
    job_store.enqueue(db, "HR_SUBMIT", "hr-submit:" + submission.id, {"submission_id": submission.id})
    db.add(
        AuditLog(
            case_id=case.id, actor=user.username, action="HR_SUBMISSION_RETRIED", after={"submission_id": submission.id}
        )
    )
    db.commit()
    return model_dict(submission)
