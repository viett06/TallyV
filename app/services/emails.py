from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.i18n import message
from app.core.serialization import model_dict as record
from app.crud import catalog as catalog_crud
from app.crud import emails as email_crud
from app.crud import jobs as job_crud
from app.schema.cases import CycleFilter


def list_emails(
    db: Session, period: str = "", department: str = "", cycle: CycleFilter = "", source: str = ""
) -> list[dict]:
    items = []
    for email in email_crud.list_emails(db, period, department, cycle, source):
        files = [{k: v for k, v in record(a).items() if k != "path"} for a in email_crud.list_attachments(db, email.id)]
        source_ids = [a["id"] for a in files] + [a["duplicate_of"] for a in files if a["duplicate_of"]]
        case_count = email_crud.case_count(db, source_ids)
        items.append(
            {
                **record(email),
                "attachments": files,
                "case_count": case_count,
                "department": catalog_crud.get_department(db, email.department_id).name
                if email.department_id
                else message("emails.department_unrecognized"),
            }
        )
    return items


def email_detail(db: Session, email_id: int) -> dict:
    email = email_crud.get_email(db, email_id)
    if not email:
        raise AppError(404, message("emails.not_found"))
    attachments = email_crud.list_attachments(db, email_id)
    batches = [record(x) for x in email_crud.list_batches(db, [a.id for a in attachments])]
    versions = email_crud.list_versions(db, [a.id for a in attachments])
    return {
        **record(email),
        "attachments": [{k: v for k, v in record(a).items() if k != "path"} for a in attachments],
        "batches": batches,
        "cases": [
            {"id": v.case_id, "code": v.normalized["code"], "row": v.row_number, "version_status": v.status}
            for v in versions
        ],
    }


def retry_email(db: Session, email_id: int) -> dict:
    email = email_crud.get_email(db, email_id)
    if email and email.status == "NEEDS_REVIEW" and email.source_id.startswith("outlook:"):
        from app.crud.outlook import get_connection
        from app.services.imports import email_scope, file_scope
        from app.services.storage import stored_path

        connection = get_connection(db)
        if connection and connection.status == "CONNECTED":
            files = (
                (file.name, stored_path(file.path).read_bytes()) for file in email_crud.list_attachments(db, email.id)
            )
            period, department_name = file_scope(files)
            scope = email_scope(
                db, email.sender, email.subject, connection.mailbox, connection.mailbox, period, department_name
            )
            for field, value in scope.items():
                setattr(email, field, value)
    if not email or not email.department_id or not email.period_id or email.status == "NEEDS_REVIEW":
        raise AppError(422, message("emails.out_of_scope"))
    job = job_crud.enqueue(db, "IMPORT_EMAIL", f"email:{email.id}", {"email_id": email.id})
    db.commit()
    return {"job_id": job.id}
