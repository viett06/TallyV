from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import OutlookAuthFlow, OutlookConnection


def get_connection(db: Session, *, for_update: bool = False) -> OutlookConnection | None:
    query = select(OutlookConnection).where(OutlookConnection.id == 1)
    return db.scalar(query.with_for_update() if for_update else query)


def get_flow(db: Session, flow_id: str) -> OutlookAuthFlow | None:
    return db.scalar(select(OutlookAuthFlow).where(OutlookAuthFlow.id == flow_id).with_for_update())


def clear_flows(db: Session, owner_id: int) -> None:
    db.execute(
        delete(OutlookAuthFlow).where((OutlookAuthFlow.owner_id == owner_id) | (OutlookAuthFlow.expires_at < utcnow()))
    )
