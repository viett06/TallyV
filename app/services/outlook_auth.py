"""Delegated Microsoft sign-in, browser-bound state, and encrypted MSAL caches."""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import msal
import requests
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, MailboxReauthenticationRequired
from app.core.i18n import message
from app.core.time import utcnow
from app.crud import outlook as repository
from app.crud.jobs import enqueue, get_by_key
from app.models import OutlookAuthFlow, OutlookConnection

SCOPES = ["User.Read", "Mail.Read"]
COOKIE_NAME = "tallyv_outlook_flow"
COOKIE_PATH = "/api/outlook/callback"
FLOW_SECONDS = 600


def configured() -> bool:
    return bool(
        settings.outlook_tenant_id and settings.outlook_client_id and settings.outlook_client_secret.get_secret_value()
    )


def _cipher() -> Fernet:
    key = hashlib.sha256(("tallyv-outlook-v1:" + settings.secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _cipher().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        raise MailboxReauthenticationRequired(message("outlook.reconnect_required")) from None


def _signer():
    return URLSafeTimedSerializer(settings.secret_key, salt="tallyv-outlook-browser")


def microsoft_client(cache: msal.SerializableTokenCache):
    if not configured():
        raise AppError(409, message("outlook.configuration_required"))
    session = requests.Session()
    session.trust_env = False
    return msal.ConfidentialClientApplication(
        settings.outlook_client_id,
        authority="https://login.microsoftonline.com/" + settings.outlook_tenant_id,
        client_credential=settings.outlook_client_secret.get_secret_value(),
        token_cache=cache,
        http_client=session,
        timeout=20,
        enable_pii_log=False,
    )


def connection_status(db: Session) -> dict:
    row = repository.get_connection(db)
    sync = get_by_key(db, "mailbox-sync") if row and row.status != "DISCONNECTED" else None
    return {
        "provider": settings.mail_provider,
        "transport": settings.outlook_transport,
        "connected_transport": row.transport if row else None,
        "configured": configured(),
        "status": row.status if row else "DISCONNECTED",
        "mailbox": row.mailbox if row else "",
        "connected_at": row.connected_at if row else None,
        "last_synced_at": row.last_synced_at if row else None,
        "sync_status": sync.status if sync else None,
        "sync_error": sync.error if sync else None,
        "sync_summary": sync.payload.get("summary", {}) if sync else {},
        "sync_days": settings.outlook_sync_days,
        "redirect_uri": settings.outlook_redirect_uri,
        "test_mode": settings.outlook_test_mode,
    }


def begin_connection(db: Session, owner_id: int, origin: str) -> tuple[str, str]:
    if settings.mail_provider != "outlook" or not configured():
        raise AppError(409, message("outlook.configuration_required"))
    redirect = urlsplit(settings.outlook_redirect_uri)
    expected_origin = f"{redirect.scheme}://{redirect.netloc}"
    if origin.rstrip("/") != expected_origin:
        raise AppError(409, message("outlook.origin_required", origin=expected_origin))
    existing = repository.get_connection(db)
    if existing and existing.status != "DISCONNECTED" and existing.owner_id != owner_id:
        raise AppError(403, message("outlook.owner_required"))
    if existing and existing.status == "CONNECTED":
        raise AppError(409, message("outlook.disconnect_first"))
    cache = msal.SerializableTokenCache()
    app = microsoft_client(cache)
    flow = app.initiate_auth_code_flow(
        SCOPES,
        redirect_uri=settings.outlook_redirect_uri,
        response_mode="form_post" if redirect.scheme == "https" else "query",
        prompt="select_account",
    )
    if "auth_uri" not in flow or "state" not in flow:
        raise AppError(502, message("outlook.authorization_failed"))
    flow_id = secrets.token_urlsafe(32)
    repository.clear_flows(db, owner_id)
    db.add(
        OutlookAuthFlow(
            id=flow_id,
            owner_id=owner_id,
            payload=encrypt(json.dumps(flow)),
            expires_at=utcnow() + timedelta(seconds=FLOW_SECONDS),
        )
    )
    db.commit()
    return flow["auth_uri"], _signer().dumps(flow_id)


def read_profile(access_token: str) -> dict:
    with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
        response = client.get(
            "https://graph.microsoft.com/v1.0/me",
            params={"$select": "id,mail,userPrincipalName"},
            headers={"Authorization": "Bearer " + access_token},
        )
        response.raise_for_status()
        return response.json()


def complete_connection(db: Session, cookie: str, parameters: dict[str, str]) -> None:
    try:
        flow_id = _signer().loads(cookie, max_age=FLOW_SECONDS)
    except BadSignature:
        raise AppError(400, message("outlook.authorization_expired")) from None
    row = repository.get_flow(db, flow_id)
    if row is None or row.expires_at.replace(tzinfo=timezone.utc) < utcnow():
        raise AppError(400, message("outlook.authorization_expired"))
    flow = json.loads(decrypt(row.payload))
    if not hmac.compare_digest(str(parameters.get("state", "")), flow["state"]):
        raise AppError(400, message("outlook.authorization_expired"))
    owner_id = row.owner_id
    db.delete(row)
    db.commit()  # Consume state before external I/O; failed exchanges require a new sign-in.
    cache = msal.SerializableTokenCache()
    app = microsoft_client(cache)
    result = app.acquire_token_by_auth_code_flow(flow, parameters)
    if "access_token" not in result:
        raise AppError(400, message("outlook.authorization_failed"))
    try:
        tenant = str(UUID(result.get("id_token_claims", {}).get("tid", "")))
    except (ValueError, TypeError, AttributeError):
        raise AppError(403, message("outlook.wrong_tenant")) from None
    if settings.outlook_tenant_id != "common" and tenant != settings.outlook_tenant_id.lower():
        raise AppError(403, message("outlook.wrong_tenant"))
    profile = read_profile(result["access_token"])
    accounts = app.get_accounts()
    mailbox = (profile.get("mail") or profile.get("userPrincipalName") or "").lower()
    if not mailbox or not profile.get("id") or not accounts:
        raise AppError(400, message("outlook.authorization_failed"))
    connection = repository.get_connection(db, for_update=True)
    if connection is None:
        connection = OutlookConnection(id=1, owner_id=owner_id)
        db.add(connection)
    elif connection.status == "CONNECTED":
        raise AppError(409, message("outlook.disconnect_first"))
    connection.owner_id = owner_id
    connection.transport = "microsoft"
    connection.status, connection.mailbox = "CONNECTED", mailbox
    connection.mailbox_id, connection.account_id = profile["id"], accounts[0]["home_account_id"]
    connection.token_cache = encrypt(cache.serialize())
    connection.delta_link = None
    connection.last_synced_at = None
    connection.connected_at = utcnow()
    db.flush()
    enqueue(db, "SYNC", "mailbox-sync", {})
    db.commit()


def access_token(connection: OutlookConnection) -> str:
    cache = msal.SerializableTokenCache()
    cache.deserialize(decrypt(connection.token_cache))
    app = microsoft_client(cache)
    accounts = [account for account in app.get_accounts() if account["home_account_id"] == connection.account_id]
    result = app.acquire_token_silent_with_error(SCOPES, account=accounts[0]) if accounts else None
    if cache.has_state_changed:
        connection.token_cache = encrypt(cache.serialize())
    if not result or "access_token" not in result:
        raise MailboxReauthenticationRequired(message("outlook.reconnect_required"))
    return result["access_token"]


def disconnect(db: Session, owner_id: int) -> None:
    connection = repository.get_connection(db, for_update=True)
    if connection:
        if connection.owner_id != owner_id:
            raise AppError(403, message("outlook.owner_required"))
        connection.status, connection.token_cache, connection.delta_link = "DISCONNECTED", "", None
    repository.clear_flows(db, owner_id)
    db.commit()
