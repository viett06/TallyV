from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.i18n import message
from app.core.serialization import json_value
from app.core.serialization import model_dict as record
from app.core.time import utcnow
from app.crud import cases as case_crud
from app.crud import jobs as job_crud
from app.models import AuditLog, User
from app.schema.cases import BulkConfirmRequest, CaseFilters, CaseReviewRequest, VersionDecisionRequest


def eligible(db: Session, case, analysis) -> bool:
    proposed = case_crud.proposed_count(db, case.id)
    return bool(
        analysis
        and analysis.status == "COMPLETED"
        and analysis.assessment == "SUFFICIENT"
        and analysis.category != "UNKNOWN"
        and case.hr_status == "PENDING_REVIEW"
        and not proposed
    )


def case_item(db: Session, row) -> dict:
    case, version, result, department, email = row
    evidence_count = case_crud.evidence_count(db, version.id)
    return {
        **record(case),
        "data": version.normalized,
        "analysis": record(result),
        "department": department.name,
        "source": {
            "email_id": email.id,
            "subject": email.subject,
            "sender": email.sender,
            "attachment_id": version.attachment_id,
            "sheet": version.sheet,
            "row": version.row_number,
        },
        "evidence_count": evidence_count,
        "bulk_eligible": eligible(db, case, result),
        "proposed_count": case_crud.proposed_count(db, case.id),
    }


def list_cases(
    db: Session, selection: CaseFilters, page: int = 1, page_size: int = 15, sort: str = "code", direction: str = "asc"
) -> dict:
    page, page_size = max(1, page), min(100, max(1, page_size))
    rows, count = case_crud.paginate(db, selection, page, page_size, sort, direction)
    return {"items": [case_item(db, row) for row in rows], "total": count, "page": page, "page_size": page_size}


def case_detail(db: Session, case_id: int) -> dict:
    row = case_crud.get_row(db, case_id)
    if not row:
        raise AppError(404, message("cases.not_found"))
    result = case_item(db, row)
    versions = case_crud.list_versions(db, case_id)
    result["versions"] = []
    for version in versions:
        analysis = case_crud.get_analysis(db, version.id)
        evidence = []
        for item in case_crud.list_evidence(db, version.id):
            evidence.append(
                {**{k: v for k, v in record(item).items() if k != "path"}, "url": f"/api/evidence/{item.id}"}
            )
        result["versions"].append({**record(version), "evidence": evidence, "analysis": record(analysis)})
    result["audit"] = [record(a) for a in case_crud.list_audit(db, case_id)]
    return result


def review(db: Session, case_id: int, body: CaseReviewRequest, user: User) -> dict:
    case = case_crud.get_for_update(db, case_id)
    if not case:
        raise AppError(404, message("cases.not_found"))
    result = case_crud.get_analysis(db, case.active_version_id)
    proposed = case_crud.proposed_count(db, case.id)
    if body.status == "NEEDS_INFO" and not body.note.strip():
        raise AppError(422, message("review.note_required"))
    if body.status == "CONFIRMED":
        if proposed:
            raise AppError(409, message("review.version_decision_required"))
        if body.category == "UNKNOWN":
            raise AppError(422, message("review.category_required"))
        if not eligible(db, case, result) and case.hr_status != "CONFIRMED":
            if not body.acknowledge_exception or len(body.override_reason.strip()) < 10:
                raise AppError(422, message("review.exception_reason_required"))
    before = {
        key: json_value(getattr(case, key))
        for key in ["hr_status", "hr_category", "hr_note", "confirmed_by", "confirmed_at"]
    }
    case.hr_category, case.hr_status, case.hr_note = body.category, body.status, body.note.strip()
    case.confirmed_by = user.username if body.status == "CONFIRMED" else None
    case.confirmed_at = utcnow() if body.status == "CONFIRMED" else None
    after = {key: json_value(getattr(case, key)) for key in before}
    db.add(
        AuditLog(
            case_id=case.id,
            actor=user.username,
            action="HR_REVIEW",
            before=before,
            after=after,
            reason=body.override_reason.strip() or body.note.strip(),
        )
    )
    db.commit()
    return {"ok": True}


def bulk(db: Session, body: BulkConfirmRequest, user: User) -> dict:
    if not body.acknowledged:
        raise AppError(422, message("review.acknowledgement_required"))
    ids = sorted(set(body.ids))
    cases = case_crud.list_for_update(db, ids)
    blocked = []
    for case in cases:
        result = case_crud.get_analysis(db, case.active_version_id)
        if not eligible(db, case, result):
            blocked.append(case.code)
    if blocked or len(cases) != len(ids):
        raise AppError(409, {"message": message("review.bulk_ineligible"), "blocked": blocked})
    for case in cases:
        result = case_crud.get_analysis(db, case.active_version_id)
        before = {"hr_status": case.hr_status, "hr_category": case.hr_category}
        case.hr_status, case.hr_category = "CONFIRMED", case.hr_category or result.category
        if case.hr_category == "UNKNOWN":
            raise AppError(409, message("review.category_unresolved"))
        case.confirmed_by, case.confirmed_at = user.username, utcnow()
        db.add(
            AuditLog(
                case_id=case.id,
                actor=user.username,
                action="BULK_CONFIRM",
                before=before,
                after={"hr_status": "CONFIRMED", "hr_category": case.hr_category},
                reason=message("audit.bulk_confirmed"),
            )
        )
    db.commit()
    return {"confirmed": len(cases)}


def decide_version(db: Session, case_id: int, version_id: int, body: VersionDecisionRequest, user: User) -> dict:
    case = case_crud.get_for_update(db, case_id)
    version = case_crud.get_version(db, version_id)
    if not case or not version or version.case_id != case.id or version.status != "PROPOSED":
        raise AppError(409, message("versions.not_proposed"))
    before = {
        "active_version_id": case.active_version_id,
        "hr_status": case.hr_status,
        "hr_category": case.hr_category,
        "hr_note": case.hr_note,
    }
    if body.action == "APPLY":
        old = case_crud.get_version(db, case.active_version_id)
        old.status, version.status = "SUPERSEDED", "ACTIVE"
        case.active_version_id = version.id
        case.hr_category, case.hr_note = None, ""
    else:
        version.status = "REJECTED"
    case.hr_status, case.confirmed_at, case.confirmed_by = "PENDING_REVIEW", None, None
    db.add(
        AuditLog(
            case_id=case.id,
            actor=user.username,
            action="VERSION_" + body.action,
            before=before,
            after={"active_version_id": case.active_version_id, "version_id": version.id, "hr_status": case.hr_status},
            reason=body.reason,
        )
    )
    db.commit()
    return {"ok": True}


def reanalyze(db: Session, case_id: int, user: User) -> dict:
    case = case_crud.get_for_update(db, case_id)
    if not case:
        raise AppError(404, message("cases.not_found"))
    analysis = case_crud.get_analysis(db, case.active_version_id)
    before = {"hr_status": case.hr_status, "analysis_status": analysis.status}
    analysis.status, analysis.assessment = "PENDING", "NOT_EVALUATED"
    case.hr_status, case.confirmed_by, case.confirmed_at = "PENDING_REVIEW", None, None
    job_crud.enqueue(db, "ANALYZE", f"analysis:{case.active_version_id}", {"version_id": case.active_version_id})
    db.add(
        AuditLog(
            case_id=case.id,
            actor=user.username,
            action="REANALYZE",
            before=before,
            after={"hr_status": case.hr_status},
            reason=message("audit.reanalysis_requested"),
        )
    )
    db.commit()
    return {"ok": True}
