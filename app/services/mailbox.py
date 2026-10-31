"""Choose the configured inbox explicitly, without falling back to demo mail."""

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, MailboxReauthenticationRequired
from app.core.i18n import message
from app.core.time import utcnow
from app.crud import outlook as repository
from app.crud.catalog import list_departments
from app.services import mailbox_auth, outlook_auth
from app.services.composio_provider import ComposioOutlookProvider
from app.services.email_provider import MailpitProvider
from app.services.imports import synchronize
from app.services.outlook_provider import GraphError, OutlookProvider


def ready(db: Session) -> bool:
    if settings.mail_provider == "mailpit":
        return True
    row = repository.get_connection(db)
    return (
        mailbox_auth.configured()
        and row is not None
        and row.status == "CONNECTED"
        and row.transport == settings.outlook_transport
    )


def poll_interval() -> int:
    if settings.mail_provider == "outlook" and settings.outlook_transport == "composio":
        return settings.composio_poll_interval
    return settings.sync_interval


def synchronize_mailbox(db: Session, *, restart: bool = False, lookback_days: int | None = None) -> dict:
    if settings.mail_provider == "mailpit":
        return synchronize(db, MailpitProvider())
    connection = repository.get_connection(db, for_update=True)
    if not connection or connection.status != "CONNECTED" or connection.transport != settings.outlook_transport:
        raise AppError(409, message("outlook.connection_required"))
    try:
        if restart:
            connection.delta_link = None
        provider = (
            ComposioOutlookProvider(connection)
            if settings.outlook_transport == "composio"
            else OutlookProvider(connection, outlook_auth.access_token(connection))
        )
        if lookback_days is not None:
            provider.sync_days = lookback_days
        provider.allowed_senders = {
            sender
            for department in list_departments(db)
            for sender in department.senders
            if not sender.endswith("@demo.invalid")
        }
        result = synchronize(db, provider)
        connection.delta_link, connection.last_synced_at = provider.checkpoint, utcnow()
        result["has_more"] = provider.has_more
        result["scanned"], result["matched"] = provider.scanned, provider.matched
        return result
    except GraphError as error:
        if error.status in {401, 403}:
            raise MailboxReauthenticationRequired(message("outlook.reconnect_required")) from None
        if error.status in {429, 503}:
            failure = AppError(503, message("outlook.rate_limited"))
            failure.retry_after = error.retry_after
            raise failure from None
        raise AppError(502, message("outlook.sync_failed")) from None
    except httpx.HTTPError:
        raise AppError(502, message("outlook.sync_failed")) from None
