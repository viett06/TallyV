"""HR categories are consumed only by the privacy-gated visual assessment."""

import json

from sqlalchemy import select

from app.models import AnalysisResult
from tests.test_evidence_vlm import add_case, inference, sample
from tests.test_evidence_vlm import pipeline as pipeline


def test_hr_can_add_category_used_by_vlm(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    policy = {
        "label": "Đi công tác",
        "description": "Chọn khi nhân viên đi công tác ngoài cơ sở.",
        "require_evidence": True,
        "require_shift": False,
        "require_punch": False,
    }
    response = client.post("/api/rules", json=policy)
    assert response.status_code == 201
    rule = response.json()
    category = rule["category"]
    case_id = add_case(sessions, [sample()])
    requests = inference(monkeypatch, category=category)
    client.post("/api/analysis")
    background.finish()
    parts = json.loads(requests[0].content)["messages"][0]["content"]
    assert policy["description"] in parts[-1]["text"]
    result = client.get(f"/api/cases/{case_id}").json()["analysis"]
    assert (result["status"], result["category"], result["assessment"]) == ("COMPLETED", category, "SUFFICIENT")
    assert result["rules_version"] == rule["settings"]["version"]
    review = {"category": "MISSING_FROM_CATALOG", "status": "CONFIRMED"}
    assert client.patch(f"/api/cases/{case_id}/review", json=review).status_code == 422
    review["category"] = category
    assert client.patch(f"/api/cases/{case_id}/review", json=review).status_code == 200


def test_rule_change_invalidates_all_visual_assessments(pipeline, monkeypatch):
    sessions, client, _, background = pipeline
    case_id = add_case(sessions, [sample()])
    inference(monkeypatch)
    client.post("/api/analysis")
    background.finish()
    assert client.get(f"/api/cases/{case_id}").json()["bulk_eligible"]
    assert (
        client.put(
            "/api/rules/UNKNOWN",
            json={
                "require_evidence": True,
                "require_shift": False,
                "require_punch": False,
                "description": "Chưa đủ căn cứ.",
            },
        ).status_code
        == 200
    )
    with sessions() as db:
        assert db.scalar(select(AnalysisResult)).status == "NOT_STARTED"
