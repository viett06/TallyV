"""Exercise the read APIs now backed by separate router/schema/service/CRUD modules."""

import subprocess
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.i18n import message
from app.demo.generate import picture, workbook
from app.models import AttendanceCase, CaseVersion
from app.schema.cases import AuditView
from app.services.analysis import analyze
from tests.helpers import ingest, row


def test_all_read_views_validate_after_partial_import(context):
    sessions, client = context
    with sessions() as db:
        email, _ = ingest(
            db, workbook([row(), row("BAD-ROW", employee="MP999")], {2: [picture("MP001", "2026-10-01")]})
        )
        case = db.scalar(select(AttendanceCase))
        version = db.scalar(select(CaseVersion))
        analyze(db, version.id)
        db.commit()
        case_id, email_id = case.id, email.id

    bootstrap = client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    assert len(bootstrap.json()["departments"]) == 5
    assert len(bootstrap.json()["periods"]) >= 12
    assert bootstrap.json()["current_period"] in {period["id"] for period in bootstrap.json()["periods"]}
    assert len(bootstrap.json()["rules"]) == 4

    dashboard = client.get("/api/dashboard?period=2026-10")
    assert dashboard.status_code == 200
    assert dashboard.json()["total"] == dashboard.json()["pending"] == 1
    assert dashboard.json()["email_errors"] == 1
    assert client.get("/api/dashboard?period=2026-09").json()["total"] == 0

    cases = client.get("/api/cases?search=TEST-001&sort=date&direction=desc")
    assert cases.status_code == 200 and cases.json()["total"] == 1
    detail = client.get(f"/api/cases/{case_id}")
    assert detail.status_code == 200
    evidence = detail.json()["versions"][0]["evidence"][0]
    assert "path" not in evidence
    assert evidence["ocr_status"] == "UNAVAILABLE"
    assert client.get(evidence["url"]).status_code == 200

    emails = client.get("/api/emails?period=2026-10")
    assert emails.status_code == 200
    assert emails.json()[0]["case_count"] == 1
    assert emails.json()[0]["status"] == "PARTIAL_ERROR"
    email_detail = client.get(f"/api/emails/{email_id}")
    assert email_detail.status_code == 200
    batch = email_detail.json()["batches"][0]
    assert batch["row_count"] == batch["imported_count"] + batch["error_count"] + batch["duplicate_count"]
    assert client.get("/api/jobs").status_code == 200
    assert client.get("/api/health").json() == {"status": "ok", "data": "synthetic"}


def test_service_errors_keep_the_existing_http_contract(context):
    _, client = context
    for path, expected_message in [
        ("/api/cases/999999", message("cases.not_found")),
        ("/api/emails/999999", message("emails.not_found")),
        ("/api/evidence/999999", message("files.evidence_not_found")),
    ]:
        response = client.get(path)
        assert response.status_code == 404
        assert response.json() == {"detail": expected_message}


def test_metadata_registry_loads_without_web_settings_or_database_session():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from app.db.base_model import Base
assert 'app.core.config' not in sys.modules
assert 'app.db.session' not in sys.modules
assert 'attendance_cases' in Base.metadata.tables
for table in Base.metadata.tables.values():
    for fk in table.foreign_keys:
        assert fk.column.table.metadata is Base.metadata
""",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_response_timestamp_representation_stays_compatible():
    view = AuditView(
        id=1,
        case_id=None,
        actor="hr.demo",
        action="HR_REVIEW",
        before={},
        after={},
        reason="",
        created_at=datetime(2026, 10, 30, 8, tzinfo=timezone.utc),
    )
    assert view.model_dump(mode="json")["created_at"] == "2026-10-30T08:00:00+00:00"
