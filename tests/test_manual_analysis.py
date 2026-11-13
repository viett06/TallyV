"""Intake and explicit assessment use background PII processing, without text/OCR engines."""

from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import func, select

from app import worker
from app.core.i18n import message
from app.demo.generate import workbook
from app.models import AnalysisResult, AttendanceCase, CaseVersion, EvidenceFile, ProcessingJob
from app.services import image_background
from app.services.imports import synchronize
from tests.helpers import Provider, ingest, row
from tests.test_evidence_vlm import inference, sample
from tests.test_evidence_vlm import pipeline as pipeline


def test_scan_precedes_explicit_assessment_and_repeated_pending_click_is_idempotent(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    requests = inference(monkeypatch, category="FORGOT_CHECK")
    with sessions() as db:
        synchronize(db, Provider(workbook([row()], {2: [sample()]})))
        db.commit()
    assert client.get("/api/analysis").json()["importing"]
    assert client.post("/api/analysis").status_code == 409
    assert worker.run_one() and not worker.run_one()
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceCase)) == 1
        result = db.scalar(select(AnalysisResult))
        assert (result.status, result.assessment) == ("NOT_STARTED", "NOT_EVALUATED")
        assert db.scalar(select(EvidenceFile)).extracted == {}
    assert not requests
    case = client.get("/api/cases").json()["items"][0]
    assert not case["bulk_eligible"]
    assert client.get("/api/cases?category=UNKNOWN").json()["total"] == 0
    exported = load_workbook(BytesIO(client.get("/api/export").content))
    assert exported.active.cell(2, 9).value is None
    assert exported.active.cell(2, 10).value == "NOT_EVALUATED"
    assert client.post("/api/analysis").json() == {"queued": 1}
    assert client.post("/api/analysis").json() == {"queued": 0}
    assert client.get("/api/analysis").json()["processing"] == 1
    background.finish()
    assert len(requests) == 1
    with sessions() as db:
        result = db.scalar(select(AnalysisResult))
        assert result.status == "COMPLETED" and result.category == "FORGOT_CHECK"
        assert db.scalar(select(AttendanceCase)).hr_status == "PENDING_REVIEW"
        assert not list(db.scalars(select(ProcessingJob).where(ProcessingJob.kind == "ANALYZE")))
    assert client.post("/api/analysis").json() == {"queued": 0}


def test_scope_includes_proposals_excludes_other_sources_and_preserves_completed(pipeline):
    sessions, client, _, background = pipeline
    with sessions() as db:
        ingest(db, workbook([row()]))
        first = db.scalar(select(AnalysisResult))
        first.status, first.category, first.assessment = "COMPLETED", "FORGOT_CHECK", "SUFFICIENT"
        db.commit()
        ingest(db, workbook([row(explanation=message("tests.explanation.revised_device"))]), "source-2")
        ingest(db, workbook([row("OUTLOOK-001")]), "outlook:test:other")
        proposed = db.scalar(select(CaseVersion).where(CaseVersion.status == "PROPOSED"))
        proposed_id, first_id = proposed.id, first.id
    assert client.post("/api/analysis?source=mailpit&period=2026-09").json() == {"queued": 0}
    assert client.post("/api/analysis?source=mailpit&period=2026-10&department=2").json() == {"queued": 0}
    assert client.post("/api/analysis?source=mailpit&period=2026-10&department=1").json() == {"queued": 1}
    with sessions() as db:
        assert db.get(AnalysisResult, first_id).status == "COMPLETED"
        assert (
            db.scalar(select(AnalysisResult).where(AnalysisResult.version_id == proposed_id)).status
            == "WAITING_PRIVACY"
        )
        assert len(list(db.scalars(select(AnalysisResult).where(AnalysisResult.status == "NOT_STARTED")))) == 1
    background.finish()
    with sessions() as db:
        assert (
            db.scalar(select(AnalysisResult).where(AnalysisResult.version_id == proposed_id)).status == "MANUAL_REVIEW"
        )


def test_failed_assessment_can_be_requested_again_and_authentication_is_required(pipeline):
    sessions, client, _, background = pipeline
    with sessions() as db:
        ingest(db, workbook([row()]))
        result = db.scalar(select(AnalysisResult))
        result.status, result.error = "FAILED", "A previous error"
        case = db.scalar(select(AttendanceCase))
        case.hr_status, case.confirmed_by = "CONFIRMED", "hr.demo"
        db.commit()
    assert client.post("/api/analysis").json() == {"queued": 1}
    with sessions() as db:
        result = db.scalar(select(AnalysisResult))
        assert result.status == "WAITING_PRIVACY" and result.error is None
        case = db.scalar(select(AttendanceCase))
        assert case.hr_status == "PENDING_REVIEW" and case.confirmed_by is None
    background.finish()
    client.post("/api/auth/logout")
    assert client.get("/api/analysis").status_code == 401
    assert client.post("/api/analysis").status_code == 401


def test_background_failure_remains_visible_and_retry_recovers(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    with sessions() as db:
        ingest(db, workbook([row()], {2: [sample()]}))
    requests = inference(monkeypatch)
    actual = image_background._preprocess

    def fail(*args):
        raise RuntimeError("simulated preprocessing failure")

    monkeypatch.setattr(image_background, "_preprocess", fail)
    client.post("/api/analysis")
    background.finish()
    assert not requests and client.get("/api/analysis").json()["failed"] == 1
    monkeypatch.setattr(image_background, "_preprocess", actual)
    client.post("/api/analysis")
    background.finish()
    assert len(requests) == 1 and client.get("/api/analysis").json()["completed"] == 1
