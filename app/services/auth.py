"""HR authentication independent of HTTP request/response objects."""

import threading
import time

from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.i18n import message
from app.crud.catalog import find_user, get_user
from app.models import User
from app.services.security import signer, verify_password

_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


def authenticate(db: Session, username: str, password: str, address: str) -> User:
    with _attempts_lock:
        recent = [stamp for stamp in _attempts.get(address, []) if stamp > time.monotonic() - 60]
        if len(recent) >= 10:
            raise AppError(429, message("auth.rate_limited"))
        _attempts[address] = [*recent, time.monotonic()]
    user = find_user(db, username)
    if not user or not verify_password(password, user.password_hash) or user.role != "HR":
        raise AppError(401, message("auth.invalid_credentials"))
    with _attempts_lock:
        _attempts.pop(address, None)
    return user


def resolve_user(db: Session, token: str | None) -> User:
    try:
        payload = signer.loads(token or "", max_age=8 * 3600)
        user = get_user(db, payload["id"])
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        raise AppError(401, message("auth.login_required"))
    if not user or user.role != "HR":
        raise AppError(403, message("auth.hr_role_required"))
    return user
