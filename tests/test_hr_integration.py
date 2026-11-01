"""Exercise the main API -> durable queue -> HTTP HR API, with isolated storage."""

from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import hr_mock_app
from app import worker
from app.core.i18n import message
from app.core.time import utcnow
from app.db.session import get_session
from app.demo.generate import picture, workbook
from app.models import HrSubmission, MockHrAttendance, MockHrReceipt, ProcessingJob
from app.services import hr_connector
from tests.helpers import ingest, row


@pytest.fixture
def hr_context(context, monkeypatch):
    sessions, client = context

    def dependency():
        with sessions() as db:
            yield db

    hr_mock_app.app.dependency_overrides[get_session] = dependency
    original_client = httpx.Client
    with TestClient(hr_mock_app.app) as target:

        def transport(request):
            response = target.request(
                request.method, request.url.raw_path.decode(), headers=request.headers, content=request.content
            )
            return httpx.Response(response.status_code, headers=response.headers, content=response.content)

        monkeypatch.setattr(
            hr_connector.httpx,
            "Client",
            lambda **kwargs: original_client(transport=httpx.MockTransport(transport), **kwargs),
        )
        monkeypatch.setattr(worker, "SessionLocal", sessions)
        with sessions() as db:
            ingest(db, workbook([row()], {2: [picture("MP001", "2026-10-01")]}))
        assert client.post("/api/analysis").json() == {"queued": 1}
        drain()
        case_id = client.get("/api/cases").json()["items"][0]["id"]
        assert (
            client.patch(
                f"/api/cases/{case_id}/review",
                json={
                    "category": "FORGOT_CHECK",
                    "status": "CONFIRMED",
                    "acknowledge_exception": True,
                    "override_reason": "Đã kiểm tra bằng chứng mô phỏng đầy đủ.",
                },
            ).status_code
            == 200
        )
        assert client.post("/api/hr/demo/seed").json() == {"created": 1}
        yield sessions, client, target, case_id
    hr_mock_app.app.dependency_overrides.clear()


def drain():
    for _ in range(10):
        if not worker.run_one():
            return
    raise AssertionError("Worker did not drain the demo queue")


def proposal(client, case_id):
    response = client.get(f"/api/hr/cases/{case_id}")
    assert response.status_code == 200, response.text
    preview = response.json()
    return {
        **preview["suggested"],
        "version_id": preview["version_id"],
        "review_token": preview["review_token"],
        "expected_revision": preview["record"]["revision"],
        "reason": "Bổ sung giờ vào theo bằng chứng và lịch ca demo.",
        "acknowledged": True,
    }


def submit(client, case_id, payload=None):
    return client.post(f"/api/hr/cases/{case_id}/submit", json=payload or proposal(client, case_id))


def test_end_to_end_hr_correction_is_manual_durable_and_idempotent(hr_context):
    sessions, client, target, case_id = hr_context
    before = client.get(f"/api/hr/cases/{case_id}").json()
    assert before["record"]["check_in"] is None
    assert before["record"]["check_out"] == "16:00"
    assert before["can_submit"]
    payload = proposal(client, case_id)
    queued = submit(client, case_id, payload)
    assert queued.status_code == 200, queued.text
    request = queued.json()
    assert request["status"] == "QUEUED"
    assert submit(client, case_id, payload).json()["id"] == request["id"]
    with sessions() as db:
        assert db.scalar(select(MockHrAttendance)).revision == 1
        assert db.scalar(select(func.count()).select_from(HrSubmission)) == 1
    drain()
    preview = client.get(f"/api/hr/cases/{case_id}").json()
    assert preview["record"]["check_in"] == "08:00"
    assert preview["record"]["revision"] == 2
    assert preview["submissions"][0]["status"] == "APPLIED"
    assert preview["submissions"][0]["receipt"]["before"]["check_in"] is None
    assert submit(client, case_id, payload).json()["id"] == request["id"]
    # Repeating demo setup must not overwrite the accepted correction.
    assert client.post("/api/hr/demo/seed").json() == {"created": 0}
    assert client.get(f"/api/hr/cases/{case_id}").json()["record"]["revision"] == 2
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["hr_submission"]["status"] == "APPLIED"
    assert {"HR_SUBMISSION_REQUESTED", "HR_SUBMISSION_APPLIED"} <= {a["action"] for a in detail["audit"]}
    # The service API rejects browser/anonymous callers.
    assert target.post("/api/attendance/lookup", json={"ids": []}).status_code == 401


@pytest.mark.parametrize("mutation", ["unconfirmed", "not_analyzed", "proposal", "stale_review", "stale_target"])
def test_submit_rechecks_review_source_and_target_version(hr_context, mutation):
    sessions, client, _, case_id = hr_context
    payload = proposal(client, case_id)
    if mutation == "unconfirmed":
        client.patch(f"/api/cases/{case_id}/review", json={"category": "FORGOT_CHECK", "status": "PENDING_REVIEW"})
    elif mutation == "not_analyzed":
        client.post(f"/api/cases/{case_id}/reanalyze")
    elif mutation == "proposal":
        with sessions() as db:
            ingest(db, workbook([row(explanation=message("tests.explanation.revised_device"))]), "revision-email")
    elif mutation == "stale_review":
        client.patch(
            f"/api/cases/{case_id}/review",
            json={"category": "FORGOT_CHECK", "status": "CONFIRMED", "note": "Kết luận mới"},
        )
    else:
        with sessions() as db:
            record = db.scalar(select(MockHrAttendance))
            record.revision += 1
            db.commit()
    assert submit(client, case_id, payload).status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(HrSubmission)) == 0
        assert db.scalar(select(func.count()).select_from(MockHrReceipt)) == 0


def test_worker_cancels_request_if_review_changes_before_send(hr_context):
    sessions, client, _, case_id = hr_context
    assert submit(client, case_id).status_code == 200
    assert client.post(f"/api/cases/{case_id}/reanalyze").status_code == 200
    drain()
    with sessions() as db:
        assert db.scalar(select(HrSubmission)).status == "CANCELLED"
        assert db.scalar(select(MockHrAttendance)).revision == 1
        assert db.scalar(select(func.count()).select_from(MockHrReceipt)) == 0


def test_target_change_after_queue_does_not_overwrite_newer_record(hr_context):
    sessions, client, _, case_id = hr_context
    assert submit(client, case_id).status_code == 200
    with sessions() as db:
        record = db.scalar(select(MockHrAttendance))
        record.check_in = "08:15"
        record.revision += 1
        db.commit()
    drain()
    preview = client.get(f"/api/hr/cases/{case_id}").json()
    assert preview["submissions"][0]["status"] == "FAILED"
    assert preview["record"]["check_in"] == "08:15"
    assert preview["record"]["revision"] == 2


def test_lost_response_reconciles_receipt_without_second_update(hr_context, monkeypatch):
    sessions, client, _, case_id = hr_context
    request_id = submit(client, case_id).json()["id"]
    actual_apply = hr_connector.connector.apply

    def lose_response(*args):
        actual_apply(*args)
        raise httpx.ReadTimeout("Response lost after HR committed")

    monkeypatch.setattr(hr_connector.connector, "apply", lose_response)
    assert worker.run_one()
    with sessions() as db:
        assert db.scalar(select(MockHrAttendance)).revision == 2
        assert db.scalar(select(HrSubmission)).status == "QUEUED"
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "HR_SUBMIT"))
        job.available_at = utcnow() - timedelta(seconds=1)
        db.commit()
    # Even a changed review cannot hide a correction the target already accepted.
    client.post(f"/api/cases/{case_id}/reanalyze")
    drain()
    with sessions() as db:
        assert db.get(HrSubmission, request_id).status == "APPLIED"
        assert db.scalar(select(MockHrAttendance)).revision == 2
        assert db.scalar(select(func.count()).select_from(MockHrReceipt)) == 1


def test_terminal_network_failure_is_visible_and_retry_recovers(hr_context, monkeypatch):
    sessions, client, _, case_id = hr_context
    request_id = submit(client, case_id).json()["id"]
    with sessions() as db:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "HR_SUBMIT"))
        job.max_attempts = 1
        db.commit()
    actual_apply = hr_connector.connector.apply

    def fail(*args):
        raise httpx.ConnectError("Simulator offline")

    monkeypatch.setattr(hr_connector.connector, "apply", fail)
    assert worker.run_one()
    assert client.get(f"/api/hr/cases/{case_id}").json()["submissions"][0]["status"] == "FAILED"
    monkeypatch.setattr(hr_connector.connector, "apply", actual_apply)
    assert client.post(f"/api/hr/submissions/{request_id}/retry").status_code == 200
    drain()
    assert client.get(f"/api/hr/cases/{case_id}").json()["submissions"][0]["status"] == "APPLIED"


@pytest.mark.parametrize(
    "changes",
    [
        {"acknowledged": False},
        {"check_in": "25:00"},
        {"check_in": "18:00", "check_out": "16:00"},
        {"check_in": None},
        {"reason": "          "},
        {"day_status": "LEAVE", "check_in": None, "check_out": None},
    ],
)
def test_invalid_correction_never_reaches_target(hr_context, changes):
    sessions, client, _, case_id = hr_context
    payload = {**proposal(client, case_id), **changes}
    assert submit(client, case_id, payload).status_code == 422
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(HrSubmission)) == 0
        assert db.scalar(select(MockHrAttendance)).revision == 1


def test_hr_endpoints_require_login(hr_context):
    _, client, _, case_id = hr_context
    payload = proposal(client, case_id)
    client.post("/api/auth/logout")
    assert client.get("/api/hr/workspace").status_code == 401
    assert client.get(f"/api/hr/cases/{case_id}").status_code == 401
    assert client.post("/api/hr/demo/seed").status_code == 401
    assert submit(client, case_id, payload).status_code == 401


@pytest.mark.parametrize(
    "shift, expected", [("AM", ("08:00", "16:00")), ("PM", ("13:00", "21:00")), ("Ca chưa có lịch", (None, None))]
)
def test_demo_schedule_prefills_only_known_shifts(hr_context, shift, expected):
    sessions, client, _, _ = hr_context
    source = row("SHIFT-002", day="2026-10-02")
    source[5] = shift
    with sessions() as db:
        ingest(db, workbook([source]), "shift-email")
    client.post("/api/analysis")
    drain()
    item = next(c for c in client.get("/api/cases").json()["items"] if c["code"] == "SHIFT-002")
    client.patch(
        f"/api/cases/{item['id']}/review",
        json={
            "category": "FORGOT_CHECK",
            "status": "CONFIRMED",
            "acknowledge_exception": True,
            "override_reason": "Kiểm tra trường hợp lịch ca mô phỏng.",
        },
    )
    assert client.post("/api/hr/demo/seed").json() == {"created": 1}
    preview = client.get(f"/api/hr/cases/{item['id']}").json()
    assert (preview["suggested"]["check_in"], preview["suggested"]["check_out"]) == expected


def test_http_target_replays_receipt_and_rejects_changed_payload(hr_context):
    sessions, client, target, case_id = hr_context
    request = submit(client, case_id).json()
    drain()
    path = f"/api/attendance/{request['payload']['record_id']}/corrections/{request['id']}"
    headers = {"Authorization": "Bearer " + hr_connector.mock_api_key()}
    payload = request["payload"]["correction"]
    assert target.put(path, json=payload, headers=headers).status_code == 200
    assert target.put(path, json={**payload, "check_in": "08:05"}, headers=headers).status_code == 409
    with sessions() as db:
        assert db.scalar(select(MockHrAttendance)).revision == 2
        assert db.scalar(select(func.count()).select_from(MockHrReceipt)) == 1


def test_outlook_and_mailpit_targets_are_separate(hr_context):
    sessions, client, _, case_id = hr_context
    with sessions() as db:
        ingest(db, workbook([row("OUTLOOK-002")]), "outlook:test:source-2")
    client.post("/api/analysis?source=all")
    drain()
    assert client.post("/api/hr/demo/seed?source=all").json() == {"created": 1}
    assert submit(client, case_id).status_code == 200
    drain()
    with sessions() as db:
        records = {r.source: r for r in db.scalars(select(MockHrAttendance))}
        assert records["mailpit"].check_in == "08:00" and records["mailpit"].revision == 2
        assert records["outlook"].check_in is None and records["outlook"].revision == 1


def test_manual_retry_reconciles_accepted_request_even_after_review_changed(hr_context, monkeypatch):
    sessions, client, _, case_id = hr_context
    request_id = submit(client, case_id).json()["id"]
    with sessions() as db:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "HR_SUBMIT"))
        job.max_attempts = 1
        db.commit()
    actual = hr_connector.connector.apply

    def lose_response(*args):
        actual(*args)
        raise httpx.ReadTimeout("Last attempt lost response")

    monkeypatch.setattr(hr_connector.connector, "apply", lose_response)
    assert worker.run_one()
    client.post(f"/api/cases/{case_id}/reanalyze")
    response = client.post(f"/api/hr/submissions/{request_id}/retry")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPLIED"
    with sessions() as db:
        assert db.scalar(select(MockHrAttendance)).revision == 2
        assert db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "HR_SUBMIT")).status == "DONE"
