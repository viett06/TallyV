from fastapi import APIRouter

from app.api.deps import DBSession
from app.core.config import settings
from app.crud.health import check_database
from app.schema.common import HealthView

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthView)
def health(db: DBSession):
    check_database(db)
    return {
        "status": "ok",
        "data": "synthetic"
        if settings.mail_provider == "mailpit"
        else "outlook_mvp"
        if settings.outlook_test_mode
        else "outlook",
    }
