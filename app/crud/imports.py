"""Intake identity queries. SHA/fingerprint constraints remain enforced by the database."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Attachment, AttendanceCase, CaseVersion, Email, ImportBatch


def get_batch(db: Session, attachment_id: int) -> ImportBatch | None:
    return db.scalar(select(ImportBatch).where(ImportBatch.attachment_id == attachment_id))


def find_duplicate_attachment(db: Session, attachment: Attachment, email: Email) -> Attachment | None:
    source = Email.source_id.startswith("outlook:")
    if not email.source_id.startswith("outlook:"):
        source = ~source
    return db.scalar(
        select(Attachment)
        .join(Email, Email.id == Attachment.email_id)
        .where(
            source,
            Email.period_id == email.period_id,
            Email.department_id == email.department_id,
            Attachment.sha256 == attachment.sha256,
            Attachment.id != attachment.id,
            Attachment.status.in_(["IMPORTED", "PARTIAL_ERROR"]),
        )
        .order_by(Attachment.id)
    )


def active_source(db: Session, case: AttendanceCase) -> str:
    return (
        db.scalar(
            select(Email.source_id)
            .join(Attachment, Attachment.email_id == Email.id)
            .join(CaseVersion, CaseVersion.attachment_id == Attachment.id)
            .where(CaseVersion.id == case.active_version_id)
        )
        or ""
    )


def find_case_for_update(db: Session, code: str) -> AttendanceCase | None:
    return db.scalar(select(AttendanceCase).where(AttendanceCase.code == code).with_for_update())


def find_version(db: Session, case_id: int, fingerprint: str) -> CaseVersion | None:
    return db.scalar(select(CaseVersion).where(CaseVersion.case_id == case_id, CaseVersion.fingerprint == fingerprint))


def email_exists(db: Session, source_id: str, message_id: str | None) -> bool:
    conditions = [Email.source_id == source_id]
    if message_id:
        conditions.append(Email.message_id == message_id)
    return db.scalar(select(Email.id).where(or_(*conditions))) is not None
