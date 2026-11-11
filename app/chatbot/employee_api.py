from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import DBSession
from app.chatbot.library import DocumentType, browse
from app.chatbot.retrieval import answer_question
from app.core.config import settings
from app.models import User
from app.schema.auth import LoginRequest, UserView
from app.services.auth import authenticate, resolve_user
from app.services.security import signer

router = APIRouter(prefix="/employee")
SESSION_COOKIE = "tallyv_employee_session"


def current_employee(request: Request, db: DBSession) -> User:
    return resolve_user(db, request.cookies.get(SESSION_COOKIE), role="EMPLOYEE")


EmployeeUser = Annotated[User, Depends(current_employee)]


class Question(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True), Field(min_length=3, max_length=800)]


@router.post("/login", response_model=UserView)
def login(body: LoginRequest, request: Request, response: Response, db: DBSession):
    user = authenticate(
        db, body.username, body.password, request.client.host if request.client else "local", role="EMPLOYEE"
    )
    response.set_cookie(
        SESSION_COOKIE,
        signer.dumps({"id": user.id}),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=8 * 3600,
        path="/api/chatbot/employee",
    )
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/api/chatbot/employee")
    return {"ok": True}


@router.get("/me", response_model=UserView)
def me(user: EmployeeUser):
    return user


@router.post("/ask")
def ask(body: Question, db: DBSession, user: EmployeeUser):
    return answer_question(db, body.question)


@router.get("/library")
def library(
    db: DBSession,
    user: EmployeeUser,
    q: Annotated[str, Query(max_length=120)] = "",
    document_type: DocumentType | None = None,
    document_id: Annotated[int | None, Query(gt=0)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
):
    return browse(db, keyword=q, document_type=document_type, document_id=document_id, page=page)
