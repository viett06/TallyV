"""Run separately: uvicorn hr_mock_app:app --host 127.0.0.1 --port 8010."""

import hmac
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from app.api.deps import DBSession
from app.core.errors import AppError
from app.core.i18n import message
from app.crud import mock_hr as store
from app.schema.hr import MockApplyRequest, MockAttendanceView, MockLookupRequest, MockReceiptView, MockSeedRequest
from app.services import mock_hr
from app.services.hr_connector import mock_api_key


def authenticate(authorization: Annotated[str | None, Header()] = None):
    if not hmac.compare_digest(authorization or "", "Bearer " + mock_api_key()):
        raise AppError(401, message("hr.service_auth_required"))


app = FastAPI(
    title="TallyV HR Simulator (not SAP)",
    dependencies=[Depends(authenticate)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.exception_handler(AppError)
async def application_error(request: Request, error: AppError):
    return JSONResponse({"detail": error.detail}, status_code=error.status_code)


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "MOCK_HR"}


@app.post("/api/attendance/lookup", response_model=list[MockAttendanceView])
def lookup(body: MockLookupRequest, db: DBSession):
    return store.list_records(db, body.ids)


@app.post("/api/demo/seed")
def seed(body: MockSeedRequest, db: DBSession):
    return mock_hr.seed(db, body)


@app.get("/api/corrections/{request_id}", response_model=MockReceiptView)
def receipt(request_id: UUID, db: DBSession):
    result = store.get_receipt(db, str(request_id))
    if not result:
        raise AppError(404, message("hr.target_record_missing"))
    return result


@app.put("/api/attendance/{record_id}/corrections/{request_id}", response_model=MockReceiptView)
def correct(record_id: str, request_id: UUID, body: MockApplyRequest, db: DBSession):
    return mock_hr.apply(db, record_id, str(request_id), body)
