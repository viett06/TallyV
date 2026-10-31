"""Email intake, partial imports, deduplication and version proposals in one transaction."""

import hashlib
import json
import re
from datetime import date
from zipfile import BadZipFile

from sqlalchemy.orm import Session

from app.core.i18n import message
from app.crud import catalog as catalog_crud
from app.crud import emails as email_crud
from app.crud import imports as import_crud
from app.crud.jobs import enqueue
from app.models import (
    AnalysisResult,
    Attachment,
    AttendanceCase,
    AuditLog,
    CaseVersion,
    Email,
    EvidenceFile,
    ImportBatch,
)
from app.services.catalog import ensure_period
from app.services.email_provider import EmailProvider
from app.services.excel import MAX_BYTES, parse_workbook
from app.services.review_calendar import parse_cycle, payroll_period
from app.services.storage import store_bytes, stored_path


def ingest_attachment(db: Session, attachment: Attachment) -> None:
    email = email_crud.get_email(db, attachment.email_id)
    batch = import_crud.get_batch(db, attachment.id)
    if batch is None:
        batch = ImportBatch(attachment_id=attachment.id)
        db.add(batch)
        db.flush()
    # Retrying a partial file replays valid rows; unique fingerprints make this idempotent.
    batch.errors, batch.row_count, batch.imported_count, batch.error_count, batch.duplicate_count = [], 0, 0, 0, 0
    duplicate = import_crud.find_duplicate_attachment(db, attachment, email)
    if duplicate:
        attachment.duplicate_of = duplicate.id
        source_batch = import_crud.get_batch(db, duplicate.id)
        if source_batch:
            batch.row_count = source_batch.row_count
            batch.duplicate_count = source_batch.imported_count + source_batch.duplicate_count
            batch.error_count = source_batch.error_count
            batch.errors = source_batch.errors
        attachment.status = "PARTIAL_ERROR" if duplicate.status == "PARTIAL_ERROR" else "DUPLICATE"
        attachment.error = duplicate.error
        return
    try:
        parsed, errors, count, global_errors = parse_workbook(stored_path(attachment.path).read_bytes())
        batch.row_count = count
        batch.errors = errors + [{"row": None, "codes": [e]} for e in global_errors]
        batch.error_count = len(errors)
        for item in parsed:
            n = item["normalized"]
            employee = catalog_crud.get_employee(db, n["employee_id"])
            department = catalog_crud.get_department(db, employee.department_id) if employee else None
            issues = []
            if not employee:
                issues.append(message("imports.employee_unknown"))
            elif n["department"] != department.name or employee.department_id != email.department_id:
                issues.append(message("imports.department_mismatch"))
            if employee and n["name"] != employee.name:
                issues.append(message("imports.employee_name_mismatch"))
            period = catalog_crud.get_period(db, email.period_id)
            occurred = date.fromisoformat(n["date"])
            if not period or not period.starts <= occurred <= period.ends:
                issues.append(message("imports.date_outside_period"))
            if issues:
                batch.errors = [*batch.errors, {"row": item["row"], "codes": issues, "raw": item["raw"]}]
                batch.error_count += 1
                continue
            fingerprint = hashlib.sha256(
                json.dumps(
                    {"data": n, "images": sorted(x["hash"] for x in item["images"])}, sort_keys=True, ensure_ascii=False
                ).encode()
            ).hexdigest()
            case = import_crud.find_case_for_update(db, n["code"])
            if case and import_crud.active_source(db, case).startswith("outlook:") != email.source_id.startswith(
                "outlook:"
            ):
                batch.errors = [
                    *batch.errors,
                    {"row": item["row"], "codes": [message("imports.source_conflict")], "raw": item["raw"]},
                ]
                batch.error_count += 1
                continue
            if case and (case.employee_id != employee.id or case.period_id != email.period_id):
                batch.errors = [
                    *batch.errors,
                    {
                        "row": item["row"],
                        "codes": [message("imports.case_identity_conflict")],
                        "raw": item["raw"],
                    },
                ]
                batch.error_count += 1
                continue
            if case and import_crud.find_version(db, case.id, fingerprint):
                batch.duplicate_count += 1
                continue
            is_new = case is None
            if is_new:
                case = AttendanceCase(
                    code=n["code"],
                    employee_id=employee.id,
                    department_id=employee.department_id,
                    period_id=email.period_id,
                    cycle_start=email.cycle_start,
                )
                db.add(case)
                db.flush()
            version = CaseVersion(
                case_id=case.id,
                attachment_id=attachment.id,
                row_number=item["row"],
                raw=item["raw"],
                normalized=n,
                fingerprint=fingerprint,
                status="ACTIVE" if is_new else "PROPOSED",
            )
            db.add(version)
            db.flush()
            if is_new:
                case.active_version_id = version.id
            else:
                before = {
                    "hr_status": case.hr_status,
                    "confirmed_by": case.confirmed_by,
                    "confirmed_at": str(case.confirmed_at),
                }
                case.hr_status, case.confirmed_by, case.confirmed_at = "PENDING_REVIEW", None, None
                db.add(
                    AuditLog(
                        case_id=case.id,
                        actor="system",
                        action="VERSION_PROPOSED",
                        before=before,
                        after={"version_id": version.id, "hr_status": case.hr_status},
                        reason=message("audit.version_proposed"),
                    )
                )
            for picture in item["images"]:
                path, sha = store_bytes(picture["content"], ".png")
                db.add(EvidenceFile(version_id=version.id, path=path, sha256=sha, anchor=picture["anchor"]))
            db.add(AnalysisResult(version_id=version.id, status="NOT_STARTED", assessment="NOT_EVALUATED"))
            batch.imported_count += 1
        attachment.error = message("imports.partial_error") if batch.errors else None
        attachment.status = (
            ("PARTIAL_ERROR" if batch.imported_count + batch.duplicate_count else "FAILED")
            if batch.errors
            else "IMPORTED"
        )
    except (ValueError, BadZipFile, KeyError, OSError):
        attachment.status, attachment.error = (
            "FAILED",
            message("imports.workbook_failed"),
        )
        batch.errors = [{"row": None, "codes": [attachment.error]}]
    db.flush()


def process_email(db: Session, email_id: int) -> None:
    email = email_crud.get_email(db, email_id)
    if not email or not email.department_id or not email.period_id or email.status == "NEEDS_REVIEW":
        return
    email.status, email.error = "PROCESSING", None
    attachments = email_crud.list_attachments(db, email.id)
    spreadsheets = [a for a in attachments if a.name.lower().endswith(".xlsx")]
    if not spreadsheets:
        email.status, email.error = "FAILED", message("imports.workbook_missing")
        return
    for attachment in spreadsheets:
        if attachment.status in {"RECEIVED", "FAILED", "PARTIAL_ERROR"}:
            ingest_attachment(db, attachment)
    batches = email_crud.list_batches(db, [a.id for a in spreadsheets])
    email.row_count = sum(b.row_count for b in batches)
    email.error_count = sum(len(b.errors) for b in batches)
    errors = [a for a in attachments if a.status in {"FAILED", "PARTIAL_ERROR", "UNSUPPORTED"}]
    email.status = (
        (
            "PARTIAL_ERROR"
            if any(a.status in {"IMPORTED", "DUPLICATE", "PARTIAL_ERROR"} for a in spreadsheets)
            else "FAILED"
        )
        if errors
        else "IMPORTED"
    )
    email.error = message("imports.email_incomplete") if errors else None


def email_scope(
    db: Session,
    sender: str,
    subject: str,
    recipients: str,
    recipient: str,
    fallback_period: str | None = None,
    department_name: str | None = None,
) -> dict:
    department = catalog_crud.find_department_by_sender(db, sender, department_name)
    match = re.search(r"\[DCC\]\s*\[(\d{4}-\d{2})\]", subject)
    try:
        period_id = match[1] if match else fallback_period
        period = ensure_period(db, period_id) if period_id else None
    except ValueError:
        period = None
    markers = re.findall(r"\[WEEK:([^\]]*)\]", subject, re.IGNORECASE)
    cycle_start = None
    invalid_cycle = bool(re.search(r"\[WEEK\s*:", subject, re.IGNORECASE)) and not markers
    if markers:
        try:
            if len(markers) != 1 or period is None:
                raise ValueError("Ambiguous or missing review month")
            cycle_start = parse_cycle(period.id, markers[0])
        except ValueError:
            invalid_cycle = True
    in_scope = department and period and not invalid_cycle and recipient in recipients.split(", ")
    return {
        "department_id": department.id if department else None,
        "period_id": period.id if period else None,
        "cycle_start": cycle_start,
        "status": "RECEIVED" if in_scope else "NEEDS_REVIEW",
        "error": None
        if in_scope
        else message("imports.invalid_cycle" if invalid_cycle else "imports.email_out_of_scope"),
    }


def file_scope(attachments) -> tuple[str | None, str | None]:
    periods, departments = set(), set()
    for name, content in attachments:
        if name.lower().endswith(".xlsx") and len(content) <= MAX_BYTES:
            try:
                rows, *_ = parse_workbook(content)
                periods.update(payroll_period(date.fromisoformat(row["normalized"]["date"])) for row in rows)
                departments.update(row["normalized"]["department"] for row in rows)
            except (ValueError, BadZipFile, KeyError, OSError):
                continue
    return next(iter(periods)) if len(periods) == 1 else None, next(iter(departments)) if len(
        departments
    ) == 1 else None


def synchronize(db: Session, provider: EmailProvider) -> dict[str, int]:
    result = {"new": 0, "existing": 0}
    for incoming in provider.messages():
        if import_crud.email_exists(db, incoming.source_id, incoming.message_id):
            result["existing"] += 1
            continue
        fallback_period, department_name = None, None
        if incoming.source_id.startswith("outlook:") and (
            not re.search(r"\[DCC\]\s*\[\d{4}-\d{2}\]", incoming.subject)
            or len(catalog_crud.departments_by_sender(db, incoming.sender)) > 1
        ):
            fallback_period, department_name = file_scope(incoming.attachments)
        scope = email_scope(
            db,
            incoming.sender,
            incoming.subject,
            incoming.recipient,
            getattr(provider, "mailbox_address", "hr@demo.invalid"),
            fallback_period,
            department_name,
        )
        if incoming.source_id.startswith("outlook:") and scope["period_id"] is None:
            scope["error"] = message("outlook.period_unknown")
        email = Email(
            source_id=incoming.source_id,
            message_id=incoming.message_id[:300] if incoming.message_id else None,
            sender=incoming.sender[:200],
            recipient=incoming.recipient[:200],
            subject=incoming.subject[:500],
            body=incoming.body,
            received_at=incoming.received_at,
            **scope,
        )
        db.add(email)
        db.flush()
        for index, (name, content) in enumerate(incoming.attachments):
            path, sha = store_bytes(content, ".bin")
            ok = name.lower().endswith(".xlsx") and len(content) <= MAX_BYTES
            db.add(
                Attachment(
                    email_id=email.id,
                    part_index=index,
                    name=name,
                    path=path,
                    sha256=sha,
                    size=len(content),
                    status="RECEIVED" if ok else "UNSUPPORTED",
                    error=None if ok else message("imports.attachment_unsupported"),
                )
            )
        if scope["status"] == "RECEIVED":
            enqueue(db, "IMPORT_EMAIL", f"email:{email.id}", {"email_id": email.id})
        result["new"] += 1
    db.flush()
    return result
