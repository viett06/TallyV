from fastapi import APIRouter

from app.api.deps import DBSession, Filters, HRUser
from app.schema.hr import HrWorkspaceView
from app.services import hr

router = APIRouter(prefix="/hr", tags=["HR integration demo"])


@router.get("/workspace", response_model=HrWorkspaceView)
def workspace(db: DBSession, selection: Filters, user: HRUser):
    return hr.workspace(db, selection)


@router.post("/demo/seed")
def seed(db: DBSession, selection: Filters, user: HRUser):
    return hr.seed(db, selection, user)
