"""Bind a Composio Connect Link to the initiating HR user and browser."""

import hmac
import json
import secrets
from datetime import timedelta, timezone
from urllib.parse import urlencode, urlsplit

import httpx
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.i18n import message
from app.core.time import utcnow
from app.crud import outlook as repository
from app.crud.jobs import enqueue
from app.models import OutlookAuthFlow, OutlookConnection
from app.services.composio_client import READ_SCOPES, ComposioClient, account_id, configured, require_mvp, user_id
from app.services.outlook_auth import FLOW_SECONDS, decrypt, encrypt
from app.services.outlook_provider import GRAPH_ROOT


def signer():
    return URLSafeTimedSerializer(settings.secret_key, salt="tallyv-composio-browser")


def begin_connection(db: Session, owner_id: int, origin: str) -> tuple[str, str]:
    require_mvp()
    if not configured():
        raise AppError(409, message("composio.configuration_required"))
    redirect = urlsplit(settings.outlook_redirect_uri)
    expected_origin = f"{redirect.scheme}://{redirect.netloc}"
    if origin.rstrip("/") != expected_origin:
        raise AppError(409, message("outlook.origin_required", origin=expected_origin))
    existing = repository.get_connection(db)
    if existing and existing.status != "DISCONNECTED" and existing.owner_id != owner_id:
        raise AppError(403, message("outlook.owner_required"))
    if existing and existing.status == "CONNECTED":
        raise AppError(409, message("outlook.disconnect_first"))
    state, flow_id = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with ComposioClient() as client:
        result = client.request(
            "POST",
            "/connected_accounts/link",
            body={
                "auth_config_id": settings.composio_auth_config_id,
                "user_id": user_id(owner_id),
                "callback_url": settings.outlook_redirect_uri + "?" + urlencode({"state": state}),
            },
        )
    remote_id = account_id(result.get("connected_account_id", ""))
    link = result.get("redirect_url", "")
    parsed = urlsplit(link)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "connect.composio.dev"
        or parsed.port not in {None, 443}
        or parsed.username
        or parsed.password
        or not parsed.path.startswith("/link/")
        or parsed.fragment
    ):
        raise AppError(502, message("outlook.authorization_failed"))
    repository.clear_flows(db, owner_id)
    db.add(
        OutlookAuthFlow(
            id=flow_id,
            owner_id=owner_id,
            payload=encrypt(json.dumps({"state": state, "account_id": remote_id, "transport": "composio"})),
            expires_at=utcnow() + timedelta(seconds=FLOW_SECONDS),
        )
    )
    db.commit()
    return link, signer().dumps(flow_id)


def complete_connection(db: Session, cookie: str, parameters: dict[str, str]) -> None:
    require_mvp()
    if not configured():
        raise AppError(409, message("composio.configuration_required"))
    try:
        flow_id = signer().loads(cookie, max_age=FLOW_SECONDS)
    except BadSignature:
        raise AppError(400, message("outlook.authorization_expired")) from None
    flow = repository.get_flow(db, flow_id)
    if flow is None or flow.expires_at.replace(tzinfo=timezone.utc) < utcnow():
        raise AppError(400, message("outlook.authorization_expired"))
    payload = json.loads(decrypt(flow.payload))
    if payload.get("transport") != "composio" or not hmac.compare_digest(
        str(parameters.get("state", "")), payload["state"]
    ):
        raise AppError(400, message("outlook.authorization_expired"))
    owner_id, remote_id = flow.owner_id, payload["account_id"]
    db.delete(flow)
    db.commit()  # Consume browser-bound state before checking any remote account.
    if parameters.get("status") != "success" or parameters.get("connected_account_id") != remote_id:
        raise AppError(400, message("outlook.authorization_failed"))
    with ComposioClient() as client:
        account = client.get_account(remote_id)
        auth_config = account.get("auth_config") or {}
        if (
            account.get("id") != remote_id
            or account.get("status") != "ACTIVE"
            or account.get("toolkit", {}).get("slug") != "outlook"
            or auth_config.get("id") != settings.composio_auth_config_id
            or not auth_config.get("is_composio_managed")
            or auth_config.get("is_disabled")
            or account.get("is_disabled")
            or (account.get("user_id") and account["user_id"] != user_id(owner_id))
        ):
            raise AppError(400, message("outlook.authorization_failed"))
        # New connections have scope snapshots. Refuse unexpected write or broader read scopes.
        scopes = {scope.rsplit("/", 1)[-1].lower() for scope in account.get("requested_scopes", [])}
        if not {"mail.read", "user.read"} <= scopes or scopes - set(READ_SCOPES.lower().split(",")):
            raise AppError(403, message("composio.read_only_scopes"))
        profile = client.graph_json(remote_id, owner_id, GRAPH_ROOT + "/me?$select=id,mail,userPrincipalName")
    mailbox = (profile.get("mail") or profile.get("userPrincipalName") or "").strip().lower()
    if "@" not in mailbox or not profile.get("id"):
        raise AppError(400, message("outlook.authorization_failed"))
    connection = repository.get_connection(db, for_update=True)
    if connection is None:
        connection = OutlookConnection(id=1, owner_id=owner_id)
        db.add(connection)
    elif connection.status == "CONNECTED":
        raise AppError(409, message("outlook.disconnect_first"))
    connection.owner_id, connection.transport, connection.status = owner_id, "composio", "CONNECTED"
    connection.mailbox, connection.mailbox_id, connection.account_id = mailbox, profile["id"], remote_id
    connection.token_cache, connection.delta_link = "", None
    connection.connected_at, connection.last_synced_at = utcnow(), None
    db.flush()
    enqueue(db, "SYNC", "mailbox-sync", {})
    db.commit()


def disconnect(db: Session, owner_id: int) -> None:
    connection = repository.get_connection(db, for_update=True)
    if connection is not None and connection.owner_id != owner_id:
        raise AppError(403, message("outlook.owner_required"))
    remote_id = connection.account_id if connection else ""
    if connection:
        connection.status, connection.token_cache, connection.delta_link = "DISCONNECTED", "", None
    repository.clear_flows(db, owner_id)
    db.commit()  # Stop all local reads even if remote revocation is unavailable.
    if remote_id:
        try:
            with ComposioClient() as client:
                client.delete_account(remote_id)
        except (AppError, ValueError, httpx.HTTPError):
            raise AppError(503, message("composio.revocation_pending")) from None
        if connection:
            connection.account_id, connection.mailbox_id = "", ""
            db.commit()
