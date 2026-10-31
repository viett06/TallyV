"""Explicit ORM column serialization; routes never inspect SQLAlchemy state."""

from typing import Any


def model_dict(instance) -> dict[str, Any] | None:
    if instance is None:
        return None
    return {column.name: getattr(instance, column.name) for column in instance.__table__.columns}


def json_value(value):
    from datetime import date, datetime

    return value.isoformat() if isinstance(value, (date, datetime)) else value
