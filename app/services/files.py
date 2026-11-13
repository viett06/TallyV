from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.i18n import message
from app.crud import emails as email_crud
from app.models import EvidencePrivacy
from app.services import evidence_privacy
from app.services.storage import read_bytes


def evidence_content(db: Session, evidence_id: int) -> bytes:
    evidence = email_crud.get_evidence(db, evidence_id)
    if evidence is None:
        raise AppError(404, message("files.evidence_not_found"))
    return read_bytes(evidence.path)


def sanitized_content(db: Session, evidence_id: int) -> bytes:
    evidence = email_crud.get_evidence(db, evidence_id)
    if evidence is None:
        raise AppError(404, message("files.evidence_not_found"))
    state = evidence_privacy.public_status(db, evidence_id)
    if not state["vlm_allowed"]:
        raise AppError(409, message("privacy.manual_required"))
    try:
        return evidence_privacy.load_image(db.get(EvidencePrivacy, evidence_id)).content
    except ValueError:
        db.commit()  # Persist invalidation so a stale READY flag cannot be reused.
        raise AppError(409, message("privacy.manual_required")) from None


def attachment_content(db: Session, attachment_id: int) -> bytes:
    attachment = email_crud.get_attachment(db, attachment_id)
    if attachment is None:
        raise AppError(404, message("files.attachment_not_found"))
    return read_bytes(attachment.path)
