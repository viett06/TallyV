from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.i18n import message
from app.core.serialization import model_dict as record
from app.core.time import utcnow
from app.crud import cases as case_crud
from app.crud import emails as email_crud
from app.crud import jobs as job_crud
from app.models import AuditLog, User
from app.schema.cases import CaseFilters
from app.schema.jobs import DemoRequest, MailboxScanRequest
from app.services import mailbox
from app.services.review_calendar import business_today, default_cycle, parse_cycle, payroll_period


def analysis_status(db: Session, selection: CaseFilters) -> dict:
    results = case_crud.list_analysis_results(db, selection)
    sync_job = job_crud.get_by_key(db, "mailbox-sync")
    emails = email_crud.list_emails(db, selection.period, selection.department, selection.cycle, selection.source)
    return {
        "waiting": sum(a.status == "NOT_STARTED" for a in results),
        "processing": sum(a.status in {"PENDING", "RUNNING"} for a in results),
        "completed": sum(a.status == "COMPLETED" for a in results),
        "failed": sum(a.status == "FAILED" for a in results),
        "importing": bool(sync_job and sync_job.status in {"PENDING", "RUNNING"})
        or any(e.status in {"RECEIVED", "PROCESSING"} for e in emails),
    }


def queue_analysis(db: Session, selection: CaseFilters, user: User) -> dict:
    if analysis_status(db, selection)["importing"]:
        raise AppError(409, message("analysis.intake_in_progress"))
    queued = 0
    rows = case_crud.list_rows(db, selection)
    cases = {case.id: case for case in case_crud.list_for_update(db, [row[0].id for row in rows])}
    for result in case_crud.list_analysis_results(db, selection, for_update=True):
        if result.status not in {"NOT_STARTED", "FAILED"}:
            continue
        version = case_crud.get_version(db, result.version_id)
        case = cases[version.case_id]
        before = {"hr_status": case.hr_status, "analysis_status": result.status}
        if case.active_version_id == result.version_id:
            case.hr_status, case.confirmed_by, case.confirmed_at = "PENDING_REVIEW", None, None
        result.status, result.assessment, result.error = "PENDING", "NOT_EVALUATED", None
        job_crud.enqueue(db, "ANALYZE", f"analysis:{result.version_id}", {"version_id": result.version_id})
        db.add(
            AuditLog(
                case_id=case.id,
                actor=user.username,
                action="ANALYSIS_REQUESTED",
                before=before,
                after={"version_id": result.version_id, "analysis_status": result.status, "hr_status": case.hr_status},
                reason=message("analysis.requested"),
            )
        )
        queued += 1
    db.commit()
    return {"queued": queued}


def sync(db: Session, body: MailboxScanRequest | None = None) -> dict:
    if not mailbox.ready(db):
        raise AppError(409, message("outlook.connection_required"))
    body = body or MailboxScanRequest(lookback_days=settings.outlook_sync_days)
    job = job_crud.enqueue(db, "SYNC", "mailbox-sync", {"mode": body.mode, "lookback_days": body.lookback_days})
    db.commit()
    return {"job_id": job.id, "status": job.status}


def demo(db: Session, body: DemoRequest) -> dict:
    if settings.mail_provider != "mailpit":
        raise AppError(409, message("outlook.demo_disabled"))
    period = body.period or payroll_period(business_today())
    try:
        cycle = parse_cycle(period, body.cycle.isoformat()) if body.cycle else default_cycle(period, business_today())
    except ValueError:
        raise AppError(422, message("imports.invalid_cycle")) from None
    payload = {"period_id": period, "cycle_start": cycle.isoformat()}
    job = job_crud.enqueue(db, "DEMO", f"demo-send:{cycle.isoformat()}", payload)
    db.commit()
    return {"job_id": job.id, "message": message("jobs.demo_queued")}


def list_jobs(db: Session) -> list[dict]:
    return [record(j) for j in job_crud.list_jobs(db)]


def retry_job(db: Session, job_id: int) -> dict:
    job = job_crud.get_job(db, job_id)
    if not job or job.status != "FAILED":
        raise AppError(409, message("jobs.retry_requires_failure"))
    job.status, job.attempts, job.error, job.available_at = "PENDING", 0, None, utcnow()
    if job.kind == "ANALYZE":
        result = case_crud.get_analysis(db, job.payload["version_id"])
        if result:
            result.status, result.error = "PENDING", None
    db.commit()
    return {"ok": True}
