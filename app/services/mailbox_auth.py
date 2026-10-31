"""Select mailbox authentication explicitly; never fall back between transports."""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import outlook as repository
from app.services import composio_auth, outlook_auth
from app.services.composio_client import configured as composio_configured
from app.services.outlook_auth import COOKIE_NAME, COOKIE_PATH, FLOW_SECONDS  # noqa: F401


def configured() -> bool:
    return composio_configured() if settings.outlook_transport == "composio" else outlook_auth.configured()


def connection_status(db: Session) -> dict:
    result = outlook_auth.connection_status(db)
    result["configured"] = configured()
    return result


def begin_connection(db: Session, owner_id: int, origin: str):
    service = composio_auth if settings.outlook_transport == "composio" else outlook_auth
    return service.begin_connection(db, owner_id, origin)


def complete_connection(db: Session, cookie: str, parameters: dict[str, str]):
    service = composio_auth if settings.outlook_transport == "composio" else outlook_auth
    return service.complete_connection(db, cookie, parameters)


def disconnect(db: Session, owner_id: int):
    connection = repository.get_connection(db)
    transport = connection.transport if connection else settings.outlook_transport
    service = composio_auth if transport == "composio" else outlook_auth
    return service.disconnect(db, owner_id)
