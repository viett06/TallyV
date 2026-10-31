from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Attachment, CaseVersion, Email, EvidenceFile, ImportBatch
from app.schema.cases import CycleFilter


def list_emails(
    db: Session, period: str = "", department: str = "", cycle: CycleFilter = "", source: str = ""
) -> list[Email]:
    query = select(Email)
    if source == "outlook":
        query = query.where(Email.source_id.startswith("outlook:"))
    elif source == "mailpit":
        query = query.where(~Email.source_id.startswith("outlook:"))
    if period:
        query = query.where(Email.period_id == period)
    if cycle == "unassigned":
        query = query.where(Email.cycle_start.is_(None))
    elif cycle:
        query = query.where(Email.cycle_start == cycle)
    if department:
        query = query.where(Email.department_id == int(department))
    return list(db.scalars(query.order_by(Email.id.desc())))


def get_email(db: Session, email_id: int) -> Email | None:
    return db.get(Email, email_id)


def list_attachments(db: Session, email_id: int) -> list[Attachment]:
    return list(db.scalars(select(Attachment).where(Attachment.email_id == email_id)))


def list_batches(db: Session, attachment_ids: list[int]) -> list[ImportBatch]:
    return list(db.scalars(select(ImportBatch).where(ImportBatch.attachment_id.in_(attachment_ids))))


def list_versions(db: Session, attachment_ids: list[int]) -> list[CaseVersion]:
    return list(db.scalars(select(CaseVersion).where(CaseVersion.attachment_id.in_(attachment_ids))))


def case_count(db: Session, attachment_ids: list[int]) -> int:
    return db.scalar(
        select(func.count(func.distinct(CaseVersion.case_id))).where(CaseVersion.attachment_id.in_(attachment_ids))
    )


def get_attachment(db: Session, attachment_id: int) -> Attachment | None:
    return db.get(Attachment, attachment_id)


def get_evidence(db: Session, evidence_id: int) -> EvidenceFile | None:
    return db.get(EvidenceFile, evidence_id)
