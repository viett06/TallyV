import json

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.demo.generate import workbook
from app.models import AttendanceCase
from app.services import analysis, gemini
from tests.helpers import ingest, row


@pytest.mark.parametrize("mode", ["RULE_BASED", "GEMINI", "LOCAL_LLM"])
def test_hr_can_add_and_use_an_attendance_category(context, monkeypatch, mode):
    sessions, client = context
    monkeypatch.setattr(settings, "processing_mode", mode)
    policy = {
        "label": "Đi công tác",
        "description": "Chọn khi nhân viên đi công tác ngoài cơ sở.",
        "keywords": ["Đi công tác"],
        "require_evidence": False,
        "require_readable_ocr": False,
        "require_shift": False,
        "require_punch": False,
    }
    response = client.post("/api/rules", json=policy)
    assert response.status_code == 201
    rule = response.json()
    category = rule["category"]
    catalog = client.get("/api/bootstrap").json()["rules"]
    assert rule in catalog and {"FORGOT_CHECK", "UNKNOWN"} <= {item["category"] for item in catalog}

    def gemini_response(payload, schema):
        case = json.loads(payload)
        assert category in schema["properties"]["category"]["enum"]
        assert case["case"]["matching_keyword_categories"] == [category]
        rule = next(item for item in case["hr_rules"] if item["category"] == category)
        assert rule["description"] == policy["description"]
        return json.dumps({"category": category, "reason": "Có giải trình đi công tác.", "evidence_matches": []})

    def ollama_response(_client, url, *, json):
        assert category in json["format"]["properties"]["category"]["enum"]
        assert policy["description"] in json["messages"][0]["content"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"message": {"content": '{"category":"' + category + '","reason":"Có giải trình đi công tác."}'}},
        )

    if mode == "GEMINI":
        monkeypatch.setattr(gemini, "_suggest_google", gemini_response)
    elif mode == "LOCAL_LLM":
        monkeypatch.setattr(httpx.Client, "post", ollama_response)

    with sessions() as db:
        ingest(db, workbook([row(explanation="Nhân viên DI CONG TAC ngoài cơ sở.")]))
        case = db.scalar(select(AttendanceCase))
        analysis.analyze(db, case.active_version_id)
        case_id = case.id
        db.commit()

    result = client.get(f"/api/cases/{case_id}").json()["analysis"]
    assert (result["status"], result["category"], result["assessment"]) == ("COMPLETED", category, "SUFFICIENT"), result
    assert result["rules_version"] == rule["settings"]["version"]
    filtered = client.get("/api/cases", params={"category": category}).json()["items"]
    assert [item["id"] for item in filtered] == [case_id]

    review = {"category": "MISSING_FROM_CATALOG", "status": "CONFIRMED"}
    assert client.patch(f"/api/cases/{case_id}/review", json=review).status_code == 422
    review["category"] = category
    assert client.patch(f"/api/cases/{case_id}/review", json=review).status_code == 200
    assert client.get(f"/api/cases/{case_id}").json()["hr_category"] == category
