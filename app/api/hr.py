from fastapi import APIRouter

from app.api.deps import DBSession, Filters, HRUser
from app.schema.hr import HrCaseView, HrSubmissionView, HrSubmitRequest, HrWorkspaceView
from app.services import hr

router = APIRouter(prefix="/hr", tags=["HR integration demo"])


@router.get("/workspace", response_model=HrWorkspaceView)
def workspace(db: DBSession, selection: Filters, user: HRUser):
    return hr.workspace(db, selection)


@router.post("/demo/seed")
def seed(db: DBSession, selection: Filters, user: HRUser):
    return hr.seed(db, selection, user)


@router.get("/cases/{case_id}", response_model=HrCaseView)
def preview(case_id: int, db: DBSession, user: HRUser):
    return hr.case_preview(db, case_id)


@router.post("/cases/{case_id}/submit", response_model=HrSubmissionView)
def submit(case_id: int, body: HrSubmitRequest, db: DBSession, user: HRUser):
    return hr.submit(db, case_id, body, user)


@router.post("/submissions/{submission_id}/retry", response_model=HrSubmissionView)
def retry(submission_id: str, db: DBSession, user: HRUser):
    return hr.retry(db, submission_id, user)
