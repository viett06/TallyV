"""Resolve the database URL without requiring web/auth settings in Alembic."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_database_url() -> URL:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    value = os.getenv("DATABASE_URL")
    if not value:
        raise ValueError("Set DATABASE_URL in .env or the environment before connecting to the database")
    url = make_url(value)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url
