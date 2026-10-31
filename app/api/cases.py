from fastapi import APIRouter

from app.api.deps import DBSession, Filters, HRUser
from app.schema.cases import (
    BulkConfirmRequest,
    BulkResult,
    CaseDetailView,
    CaseListView,
    CaseReviewRequest,
    VersionDecisionRequest,
)
from app.schema.common import OperationResult
from app.services import cases

router = APIRouter(prefix="/cases", tags=["Attendance cases"])


@router.get("", response_model=CaseListView)
def list_cases(
    db: DBSession,
    selection: Filters,
    user: HRUser,
    page: int = 1,
    page_size: int = 15,
    sort: str = "code",
    direction: str = "asc",
):
    return cases.list_cases(db, selection, page, page_size, sort, direction)


@router.get("/{case_id}", response_model=CaseDetailView)
def detail(case_id: int, db: DBSession, user: HRUser):
    return cases.case_detail(db, case_id)


@router.patch("/{case_id}/review", response_model=OperationResult)
def review(case_id: int, body: CaseReviewRequest, db: DBSession, user: HRUser):
    return cases.review(db, case_id, body, user)


@router.post("/bulk-confirm", response_model=BulkResult)
def bulk_confirm(body: BulkConfirmRequest, db: DBSession, user: HRUser):
    return cases.bulk(db, body, user)


@router.post("/{case_id}/versions/{version_id}", response_model=OperationResult)
def decide_version(case_id: int, version_id: int, body: VersionDecisionRequest, db: DBSession, user: HRUser):
    return cases.decide_version(db, case_id, version_id, body, user)


@router.post("/{case_id}/reanalyze", response_model=OperationResult)
def reanalyze(case_id: int, db: DBSession, user: HRUser):
    return cases.reanalyze(db, case_id, user)
