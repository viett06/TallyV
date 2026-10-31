from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.i18n import message
from app.crud import emails as email_crud
from app.services.storage import stored_path


def evidence_path(db: Session, evidence_id: int) -> Path:
    evidence = email_crud.get_evidence(db, evidence_id)
    if evidence is None:
        raise AppError(404, message("files.evidence_not_found"))
    return stored_path(evidence.path)


def attachment_path(db: Session, attachment_id: int) -> Path:
    attachment = email_crud.get_attachment(db, attachment_id)
    if attachment is None:
        raise AppError(404, message("files.attachment_not_found"))
    return stored_path(attachment.path)
