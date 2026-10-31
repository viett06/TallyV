from urllib.parse import urlsplit

import httpx
import requests
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from app.api.deps import DBSession, HRUser
from app.core.config import settings
from app.core.errors import AppError
from app.core.i18n import message
from app.schema.common import OperationResult
from app.schema.outlook import OutlookAuthorization, OutlookStatus
from app.services import mailbox_auth as outlook_auth
from app.services.outlook_provider import GraphError

router = APIRouter(prefix="/outlook", tags=["Microsoft 365 mailbox"])


@router.get("", response_model=OutlookStatus)
def status(db: DBSession, user: HRUser):
    return outlook_auth.connection_status(db)


@router.post("/connect", response_model=OutlookAuthorization)
def connect(request: Request, response: Response, db: DBSession, user: HRUser):
    try:
        authorization_url, cookie = outlook_auth.begin_connection(db, user.id, str(request.base_url))
    except (ValueError, httpx.HTTPError, requests.RequestException):
        raise AppError(502, message("outlook.authorization_failed")) from None
    secure = urlsplit(settings.outlook_redirect_uri).scheme == "https"
    response.set_cookie(
        outlook_auth.COOKIE_NAME,
        cookie,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        max_age=outlook_auth.FLOW_SECONDS,
        path=outlook_auth.COOKIE_PATH,
    )
    return {"authorization_url": authorization_url}


@router.api_route("/callback", methods=["GET", "POST"])
async def callback(request: Request, db: DBSession):
    try:
        if request.method == "POST":
            if len(await request.body()) > 16384:
                raise AppError(400, "OAuth response exceeds the allowed size")
            parameters = dict(await request.form(max_files=0, max_fields=20))
        else:
            parameters = dict(request.query_params)
        outlook_auth.complete_connection(db, request.cookies.get(outlook_auth.COOKIE_NAME, ""), parameters)
        result = "connected"
    except (AppError, GraphError, ValueError, httpx.HTTPError, requests.RequestException):
        db.rollback()
        result = "failed"
    response = RedirectResponse("/?outlook=" + result, status_code=303)
    response.delete_cookie(outlook_auth.COOKIE_NAME, path=outlook_auth.COOKIE_PATH)
    return response


@router.post("/disconnect", response_model=OperationResult)
def disconnect(db: DBSession, user: HRUser):
    outlook_auth.disconnect(db, user.id)
    return {"ok": True}
