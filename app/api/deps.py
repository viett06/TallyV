"""FastAPI dependencies. Services receive plain sessions/users and own transactions."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import User
from app.schema.cases import CaseFilters
from app.services.auth import resolve_user

DBSession = Annotated[Session, Depends(get_session)]


def current_user(request: Request, db: DBSession) -> User:
    return resolve_user(db, request.cookies.get("tallyv_session"))


HRUser = Annotated[User, Depends(current_user)]
Filters = Annotated[CaseFilters, Depends()]
