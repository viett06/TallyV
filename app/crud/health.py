from sqlalchemy import text
from sqlalchemy.orm import Session


def check_database(db: Session) -> None:
    db.execute(text("SELECT 1"))
