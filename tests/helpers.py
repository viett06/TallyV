from datetime import datetime, timezone

from sqlalchemy import select

from app.core.attendance import PUNCH_IN
from app.core.i18n import message
from app.demo.catalog import DEPARTMENTS
from app.models import Email
from app.services.email_provider import IncomingEmail
from app.services.imports import process_email, synchronize


def row(code="TEST-001", explanation=message("tests.explanation.forgot_check"), employee="MP001", day="2026-10-01"):
    return [
        code,
        employee,
        message("demo.first_employee"),
        DEPARTMENTS[0],
        day,
        message("demo.short_morning_shift"),
        PUNCH_IN,
        explanation,
        "",
    ]


class Provider:
    def __init__(self, content, source="source-1"):
        self.content, self.source = content, source

    def messages(self):
        return [
            IncomingEmail(
                self.source,
                f"<{self.source}@demo.invalid>",
                "department1@demo.invalid",
                "hr@demo.invalid",
                message("tests.email_subject"),
                message("common.synthetic_data"),
                datetime.now(timezone.utc),
                [("sample.xlsx", self.content)],
            )
        ]


def ingest(db, content, source="source-1"):
    result = synchronize(db, Provider(content, source))
    email = db.scalar(select(Email).where(Email.source_id == source))
    process_email(db, email.id)
    db.commit()
    return email, result
