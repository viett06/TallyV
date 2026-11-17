from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HrSubmission


def latest_submission(db: Session, case_id: int) -> HrSubmission | None:
    return db.scalar(
        select(HrSubmission)
        .where(HrSubmission.case_id == case_id)
        .order_by(HrSubmission.created_at.desc(), HrSubmission.id)
        .limit(1)
    )
