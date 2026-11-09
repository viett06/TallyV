import json

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app import worker
from app.core.config import settings
from app.demo.generate import picture, workbook
from app.models import AnalysisResult, AttendanceCase
from tests.helpers import ingest, row


@pytest.mark.parametrize(
    ("category", "supported", "overstates", "ocr_day", "verification_status", "assessment"),
    [
        ("DEVICE_ERROR", 0.85, 0.15, "01", "PASSED", "SUFFICIENT"),
        ("DEVICE_ERROR", 0.84, 0.02, "01", "NEEDS_REVIEW", "MISSING"),
        ("DEVICE_ERROR", 0.95, 0.16, "01", "NEEDS_REVIEW", "MISSING"),
        ("DEVICE_ERROR", "0.95", 0.02, "01", "UNAVAILABLE", "MISSING"),
        ("DEVICE_ERROR", None, None, "01", "UNAVAILABLE", "MISSING"),
        ("DEVICE_ERROR", 0.95, 0.02, "02", "PASSED", "CONFLICT"),
        ("UNKNOWN", None, None, "01", None, "MISSING"),
    ],
)
def test_jev_checks_gemini_proposals_without_sending_original_identifiers(
    context, monkeypatch, category, supported, overstates, ocr_day, verification_status, assessment
):
    sessions, client = context
    monkeypatch.setattr(settings, "processing_mode", "GEMINI")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("gemini-test-key"))
    monkeypatch.setattr(settings, "jev_enabled", True)
    monkeypatch.setattr(settings, "jev_api_key", SecretStr("jev-test-key"))
    monkeypatch.setattr(settings, "jev_threshold", 0.85)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr("app.services.analysis.read_text", lambda *a, **k: f"MP001 {ocr_day}/10/2026 08:03 MẤT KẾT NỐI")
    original = row(explanation="Máy mất kết nối. Liên hệ private@example.invalid.")
    with sessions() as db:
        ingest(db, workbook([original], {2: [picture("MP001", "2026-10-01")]}))
        case_id = db.scalar(select(AttendanceCase.id))

    assert client.post(f"/api/cases/{case_id}/reanalyze").status_code == 200
    requests = []
    model_reason = f"Máy mất kết nối. {original[2]} MP001 new-private@example.invalid 0912 345 678."

    def respond(request):
        requests.append(request)
        if request.url.host == "generativelanguage.googleapis.com":
            date_status = "MATCH" if ocr_day == "01" else "MISMATCH"
            text = json.dumps(
                {
                    "category": category,
                    "reason": model_reason,
                    "evidence_matches": [
                        {
                            "evidence_ref": 1,
                            "employee_match": "MATCH",
                            "work_date_match": date_status,
                            "shift_match": date_status,
                        }
                    ],
                }
            )
            return httpx.Response(
                200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}
            )
        if supported is None:
            raise httpx.ReadTimeout("Simulated timeout")
        return httpx.Response(
            200,
            json={
                "answers": {
                    "label_supported": {"type": "noul", "noul": supported},
                    "explanation_overstates": {"type": "noul", "noul": overstates},
                }
            },
        )

    http_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: http_client(transport=httpx.MockTransport(respond), **kw))
    assert worker.run_one(sessions)
    assert worker.run_one(sessions)

    hosts = ["generativelanguage.googleapis.com"]
    if verification_status:
        hosts.append("api.typesafe.ai")
    assert [request.url.host for request in requests] == hosts
    if verification_status:
        assert requests[1].url.path == "/v1/systemone"
        assert requests[1].headers["Authorization"] == "Bearer jev-test-key"
        gemini_payload = json.loads(json.loads(requests[0].content)["contents"][0]["parts"][0]["text"])
        jev_payload = json.loads(requests[1].content)
        assert set(jev_payload) == {"model", "state", "questions"}
        state = jev_payload["state"]
        assert state["case"] == gemini_payload["case"]
        assert state["hr_rule"]["category"] == category
        assert set(jev_payload["questions"]) == {"label_supported", "explanation_overstates"}
        assert all(question["type"] == "noul" for question in jev_payload["questions"].values())
        assert "may mat ket noi" in state["proposal"]["reason_signals"]
        outbound = requests[1].content.decode().casefold()
        for identifier in (
            original[2],
            "MP001",
            "TEST-001",
            "private@example.invalid",
            "0912 345 678",
            "08:03",
            gemini_payload["case_ref"],
        ):
            assert identifier.casefold() not in outbound

    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["analysis"]["category"] == category
    assert detail["analysis"]["status"] == "COMPLETED"
    assert detail["analysis"]["assessment"] == assessment
    assert detail["hr_status"] == "PENDING_REVIEW"
    verification = detail["analysis"]["extracted"].get("jev_verification")
    assert (verification and verification["status"]) == verification_status
    assert detail["bulk_eligible"] is (assessment == "SUFFICIENT")
    if assessment != "SUFFICIENT":
        assert client.post("/api/cases/bulk-confirm", json={"ids": [case_id], "acknowledged": True}).status_code == 409


def test_enabling_jev_blocks_bulk_confirmation_for_existing_unverified_gemini_result(context, monkeypatch):
    sessions, client = context
    with sessions() as db:
        ingest(db, workbook([row()]))
        case_id = db.scalar(select(AttendanceCase.id))
        result = db.scalar(select(AnalysisResult))
        result.method, result.category = "GEMINI", "DEVICE_ERROR"
        result.status, result.assessment = "COMPLETED", "SUFFICIENT"
        db.commit()

    assert client.get(f"/api/cases/{case_id}").json()["bulk_eligible"] is True
    monkeypatch.setattr(settings, "jev_enabled", True)
    assert client.get(f"/api/cases/{case_id}").json()["bulk_eligible"] is False
    assert client.post("/api/cases/bulk-confirm", json={"ids": [case_id], "acknowledged": True}).status_code == 409
