"""UTC timestamps shared by ORM defaults and application workflows."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
