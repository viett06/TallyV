from fastapi import APIRouter

from app.api.deps import DBSession, Filters, HRUser
from app.schema.common import JobQueued
from app.schema.emails import EmailDetailView, EmailListItem
from app.services import emails

router = APIRouter(prefix="/emails", tags=["Business inbox"])


@router.get("", response_model=list[EmailListItem])
def list_emails(db: DBSession, user: HRUser, selection: Filters):
    return emails.list_emails(db, selection.period, selection.department, selection.cycle, selection.source)


@router.get("/{email_id}", response_model=EmailDetailView)
def detail(email_id: int, db: DBSession, user: HRUser):
    return emails.email_detail(db, email_id)


@router.post("/{email_id}/retry", response_model=JobQueued)
def retry(email_id: int, db: DBSession, user: HRUser):
    return emails.retry_email(db, email_id)
