from fastapi import APIRouter, Request, Response

from app.api.deps import DBSession, HRUser
from app.core.config import settings
from app.schema.auth import LoginRequest, UserView
from app.schema.common import OperationResult
from app.services import auth
from app.services.security import signer

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=UserView)
def login(body: LoginRequest, request: Request, response: Response, db: DBSession):
    address = request.client.host if request.client else "local"
    user = auth.authenticate(db, body.username, body.password, address)
    response.set_cookie(
        "tallyv_session",
        signer.dumps({"id": user.id}),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=8 * 3600,
    )
    return user


@router.post("/logout", response_model=OperationResult)
def logout(response: Response, user: HRUser):
    response.delete_cookie("tallyv_session")
    return {"ok": True}


@router.get("/me", response_model=UserView)
def me(user: HRUser):
    return user
