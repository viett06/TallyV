from fastapi import APIRouter

from app.api.deps import DBSession, Filters, HRUser
from app.schema.common import OperationResult
from app.schema.jobs import (
    AnalysisQueued,
    AnalysisStatus,
    DemoQueued,
    DemoRequest,
    JobView,
    MailboxScanRequest,
    SyncQueued,
)
from app.services import jobs

router = APIRouter(tags=["Processing jobs"])


@router.get("/analysis", response_model=AnalysisStatus)
def analysis_status(db: DBSession, selection: Filters, user: HRUser):
    return jobs.analysis_status(db, selection)


@router.post("/analysis", response_model=AnalysisQueued)
def queue_analysis(db: DBSession, selection: Filters, user: HRUser):
    return jobs.queue_analysis(db, selection, user)


@router.post("/sync", response_model=SyncQueued)
def sync(db: DBSession, user: HRUser, body: MailboxScanRequest | None = None):
    return jobs.sync(db, body)


@router.post("/demo", response_model=DemoQueued)
def demo(db: DBSession, user: HRUser, body: DemoRequest | None = None):
    return jobs.demo(db, body or DemoRequest())


@router.get("/jobs", response_model=list[JobView])
def list_jobs(db: DBSession, user: HRUser):
    return jobs.list_jobs(db)


@router.post("/jobs/{job_id}/retry", response_model=OperationResult)
def retry(job_id: int, db: DBSession, user: HRUser):
    return jobs.retry_job(db, job_id)
