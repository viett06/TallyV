"""The reference attendance table uses the application database directly."""

import pytest
from sqlalchemy import select

from app.core.attendance import PUNCH_IN, PUNCH_OUT
from app.core.config import settings
from app.demo.generate import workbook
from app.models import MockHrAttendance, ProcessingJob
from tests.helpers import ingest, row


@pytest.mark.parametrize(
    ("shift", "missing", "expected"),
    [
        ("AM", PUNCH_IN, (None, "16:00")),
        ("PM", PUNCH_OUT, ("13:00", None)),
        ("Ca chưa có lịch", PUNCH_IN, (None, None)),
    ],
)
def test_demo_schedule_and_idempotent_seed(context, shift, missing, expected):
    sessions, client = context
    source = row()
    source[5:7] = [shift, missing]
    with sessions() as db:
        ingest(db, workbook([source]))

    assert client.get("/api/hr/workspace").json()["items"][0]["record"] is None
    assert client.post("/api/hr/demo/seed").json() == {"created": 1}
    assert client.post("/api/hr/demo/seed").json() == {"created": 0}
    record = client.get("/api/hr/workspace").json()["items"][0]["record"]
    assert (record["check_in"], record["check_out"]) == expected
    with sessions() as db:
        assert len(list(db.scalars(select(MockHrAttendance)))) == 1
        assert not list(db.scalars(select(ProcessingJob).where(ProcessingJob.kind == "HR_SUBMIT")))


def test_outlook_and_mailpit_seed_separate_reference_records(context):
    sessions, client = context
    with sessions() as db:
        ingest(db, workbook([row()]))
        ingest(db, workbook([row("OUTLOOK-002")]), "outlook:test:source-2")

    assert client.post("/api/hr/demo/seed?source=all").json() == {"created": 2}
    with sessions() as db:
        assert {record.source for record in db.scalars(select(MockHrAttendance))} == {"mailpit", "outlook"}


def test_demo_seed_is_restricted_to_test_data_and_authenticated_hr(context, monkeypatch):
    _, client = context
    monkeypatch.setattr(settings, "mail_provider", "outlook")
    monkeypatch.setattr(settings, "outlook_test_mode", False)
    assert client.post("/api/hr/demo/seed").status_code == 409
    client.cookies.clear()
    assert client.get("/api/hr/workspace").status_code == 401
    assert client.post("/api/hr/demo/seed").status_code == 401
