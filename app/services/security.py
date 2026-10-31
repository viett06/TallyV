import hashlib
import hmac
import os

from itsdangerous import URLSafeTimedSerializer

from app.core.config import settings

signer = URLSafeTimedSerializer(settings.secret_key, salt="tallyv-hr-session")


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$")
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000).hex()
    return hmac.compare_digest(digest, check)
