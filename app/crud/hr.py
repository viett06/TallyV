from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HrSubmission


def get_submission(db: Session, submission_id: str, *, refresh: bool = False) -> HrSubmission | None:
    return db.get(HrSubmission, submission_id, populate_existing=refresh)


def list_submissions(db: Session, case_id: int) -> list[HrSubmission]:
    return list(
        db.scalars(
            select(HrSubmission)
            .where(HrSubmission.case_id == case_id)
            .order_by(HrSubmission.created_at.desc(), HrSubmission.id)
        )
    )


def latest_submission(db: Session, case_id: int) -> HrSubmission | None:
    return db.scalar(
        select(HrSubmission)
        .where(HrSubmission.case_id == case_id)
        .order_by(HrSubmission.created_at.desc(), HrSubmission.id)
        .limit(1)
    )
