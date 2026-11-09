import json

import httpx
from pydantic import SecretStr
from sqlalchemy import select

from app import worker
from app.core.config import settings
from app.demo.generate import picture, workbook
from app.models import AttendanceCase, Employee
from app.services import gemini
from tests.helpers import ingest, row


def test_gemini_classifies_original_case_with_hr_policy_and_filtered_evidence(context, monkeypatch):
    sessions, client = context
    monkeypatch.setattr(settings, "processing_mode", "GEMINI")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("mock-key"))
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(
        "app.services.analysis.read_text",
        lambda *a, **k: "NGUYỄN VĂN KHANG | MP001 | 01/10/2026 08:03 | MẤT KẾT NỐI | Vũ Lệ Bích",
    )
    record = row(explanation="Nguyen Van Khang báo máy mất kết nối. Liên hệ khang@example.invalid.")
    record[2] = "Nguyễn Văn Khang"
    with sessions() as db:
        db.get(Employee, "MP001").name = record[2]
        db.commit()
        ingest(db, workbook([record], {2: [picture("MP001", "2026-10-01")]}))
        case_id = db.scalar(select(AttendanceCase.id))

    policy = {
        "require_evidence": True,
        "require_readable_ocr": True,
        "require_shift": True,
        "require_punch": True,
        "description": "Chỉ phân loại lỗi thiết bị khi ảnh có thông báo mất kết nối.",
    }
    assert client.put("/api/rules/DEVICE_ERROR", json=policy).status_code == 200
    assert client.post(f"/api/cases/{case_id}/reanalyze").status_code == 200

    requests = []

    def respond(request):
        requests.append(request)
        output = {
            "category": "DEVICE_ERROR",
            "reason": "Ảnh có thông báo mất kết nối.",
            "evidence_matches": [
                {"evidence_ref": 1, "employee_match": "MATCH", "work_date_match": "MATCH", "shift_match": "MATCH"}
            ],
        }
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps(output)}]},
                    }
                ]
            },
        )

    http_client = httpx.Client
    monkeypatch.setattr(gemini.httpx, "Client", lambda **kw: http_client(transport=httpx.MockTransport(respond), **kw))
    assert worker.run_one(sessions)
    assert worker.run_one(sessions)

    (request,) = requests
    assert request.url.host == "generativelanguage.googleapis.com"
    assert request.headers["x-goog-api-key"] == "mock-key" and not request.url.query
    body = json.loads(request.content)
    (part,) = body["contents"][0]["parts"]
    payload = json.loads(part["text"])
    assert len(payload["case_ref"]) == 32
    assert "may mat ket noi" in payload["case"]["explanation_signals"]
    (evidence,) = payload["case"]["evidence"]
    attendance_record = payload["case"]["attendance_record"]
    assert evidence["observed_day_index"] == attendance_record["work_day_index"]
    assert evidence["employee_ref"] == attendance_record["employee_ref"]
    assert (
        attendance_record["shift_start_index"]
        <= evidence["observed_clock_index"]
        <= attendance_record["shift_end_index"]
    )
    assert evidence["kind_from_ocr"] == "DEVICE" and "mat ket noi" in evidence["ocr_text_signals"]
    assert set(part) == {"text"}
    for identifier in (
        "nguyen van khang",
        "nguyễn văn khang",
        "mp001",
        "m p 0 0 1",
        "test-001",
        "khang@example.invalid",
        "vu le bich",
        "vũ lệ bích",
        "01/10/2026",
        "08:03",
    ):
        assert identifier not in part["text"].casefold()
    assert next(rule for rule in payload["hr_rules"] if rule["category"] == "DEVICE_ERROR") == {
        "category": "DEVICE_ERROR",
        **policy,
    }
    assert len(payload["hr_rules"]) == 4
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["data"]["name"] == record[2] and detail["data"]["employee_id"] == "MP001"
    assert detail["analysis"]["status"] == "COMPLETED"
    comparison = detail["versions"][0]["evidence"][0]["extracted"]["gemini_comparison"]
    assert comparison == {"employee_match": "MATCH", "work_date_match": "MATCH", "shift_match": "MATCH"}
    assert detail["analysis"]["category"] == "DEVICE_ERROR" and detail["analysis"]["method"] == "GEMINI"
    assert detail["hr_status"] == "PENDING_REVIEW"
    assert len(detail["analysis"]["extracted"]["hr_rule_versions"]) == 4

    assert client.put("/api/rules/FORGOT_CHECK", json=policy).status_code == 200
    assert client.get(f"/api/cases/{case_id}").json()["analysis"]["status"] == "NOT_STARTED"


def test_gemini_policy_with_identifiers_is_blocked_before_http(context, monkeypatch):
    sessions, client = context
    monkeypatch.setattr(settings, "processing_mode", "GEMINI")
    with sessions() as db:
        ingest(db, workbook([row()]))
        case_id = db.scalar(select(AttendanceCase.id))
    assert (
        client.put(
            "/api/rules/DEVICE_ERROR",
            json={
                "require_evidence": True,
                "require_readable_ocr": True,
                "require_shift": True,
                "require_punch": True,
                "description": "Ví dụ nhân viên M-P-0-0-1 quên chấm.",
            },
        ).status_code
        == 200
    )
    assert client.post(f"/api/cases/{case_id}/reanalyze").status_code == 200

    def unexpected_http(**_kwargs):
        raise AssertionError("PII should block before creating an HTTP client")

    monkeypatch.setattr(gemini.httpx, "Client", unexpected_http)
    assert worker.run_one(sessions)
    assert worker.run_one(sessions)
    result = client.get(f"/api/cases/{case_id}").json()["analysis"]
    assert result["status"] == "FAILED" and result["category"] == "UNKNOWN"
    assert "Đã chặn gửi" in result["error"]
