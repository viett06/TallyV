import io
import uuid
import zipfile

from sqlalchemy import select

from app.assistant.errors import AppError
from app.assistant.models import Artifact, AuditLog, GenerationRun
from app.core.time import utcnow
from app.models import ProcessingJob, User
from app.services.security import hash_password
from app.worker import run_one


def request(client, conversation, text, ids=None, key=None):
    response = client.post(
        f"/api/assistant/conversations/{conversation}/messages",
        json={"text": text, "attachment_ids": ids or [], "request_key": key or str(uuid.uuid4())},
    )
    assert response.status_code == 202, response.text
    return response.json()


def setup_demo(client, missing=False):
    cid = client.post("/api/assistant/conversations").json()["id"]
    demo = client.post(f"/api/assistant/conversations/{cid}/demo?missing={str(missing).lower()}").json()
    return cid, demo


def test_full_pipeline_real_files_and_idempotent_request(context):
    sessions, client = context
    cid, demo = setup_demo(client)
    key = str(uuid.uuid4())
    ids = [a["id"] for a in demo["attachments"]]
    first = request(client, cid, demo["prompt"], ids, key)
    assert request(client, cid, demo["prompt"], ids, key) == first
    assert run_one(sessions) and not run_one(sessions)
    detail = client.get("/api/assistant/conversations/" + cid).json()
    run = detail["runs"][0]
    assert run["status"] == "COMPLETED" and len(run["artifacts"]) == 5
    assert len([r for r in run["report"] if r["status"] == "NOT_SELECTED"]) == 3
    assert all(not a["reviewed"] for a in run["artifacts"])
    assert "storage_key" not in str(detail)
    response = client.get("/api/assistant/runs/" + run["id"] + "/download")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len([n for n in archive.namelist() if n.endswith(".docx")]) == 5
        assert archive.testzip() is None
    with sessions() as db:
        assert len(list(db.scalars(select(Artifact)))) == 5
        assert len(list(db.scalars(select(ProcessingJob)))) == 1


def test_missing_data_then_skip_with_conversation_context(context):
    sessions, client = context
    cid, demo = setup_demo(client, True)
    request(client, cid, demo["prompt"], [a["id"] for a in demo["attachments"]])
    run_one(sessions)
    result = client.get("/api/assistant/conversations/" + cid).json()
    assert result["runs"][0]["status"] == "NEEDS_INPUT" and not result["runs"][0]["artifacts"]
    assert result["messages"][-1]["details"]["missing"][0]["fields"] == ["Phòng ban"]
    request(client, cid, "Bỏ qua các hồ sơ thiếu dữ liệu và tạo các bản còn lại.")
    run_one(sessions)
    result = client.get("/api/assistant/conversations/" + cid).json()
    assert len(result["runs"][-1]["artifacts"]) == 4
    assert any(r["status"] == "SKIPPED" for r in result["runs"][-1]["report"])


def test_missing_data_correction_and_year_clarification(context):
    sessions, client = context
    cid, demo = setup_demo(client, True)
    request(client, cid, demo["prompt"].replace("12/2026", "12"), [a["id"] for a in demo["attachments"]])
    run_one(sessions)
    assert "năm nào" in client.get("/api/assistant/conversations/" + cid).json()["runs"][-1]["summary"]
    request(client, cid, "Năm 2026.")
    run_one(sessions)
    request(client, cid, "Bổ sung dữ liệu: bản ghi #2, trường 'Phòng ban': 'Tài chính'")
    run_one(sessions)
    run = client.get("/api/assistant/conversations/" + cid).json()["runs"][-1]
    assert run["status"] == "COMPLETED" and len(run["artifacts"]) == 5
    item = next(a for a in run["artifacts"] if a["label"] == "Trần Minh Khôi")
    assert item["provenance"]["original_values"]["Phòng ban"] == ""
    assert item["provenance"]["confirmed_values"]["Phòng ban"] == "Tài chính"


def test_edit_invalidates_review_stale_revision_and_download(context):
    sessions, client = context
    cid, demo = setup_demo(client)
    request(client, cid, demo["prompt"], [a["id"] for a in demo["attachments"]])
    run_one(sessions)
    artifact = client.get("/api/assistant/conversations/" + cid).json()["runs"][0]["artifacts"][0]
    aid = artifact["id"]
    assert client.post(f"/api/assistant/artifacts/{aid}/review", json={"revision": 1, "reviewed": True}).json()[
        "reviewed"
    ]
    p = next(p for p in artifact["paragraphs"] if p["text"].startswith("Kính gửi"))
    response = client.patch(
        "/api/assistant/artifacts/" + aid,
        json={"revision": 1, "paragraphs": [{"id": p["id"], "text": p["text"] + " (đã kiểm tra)"}]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2 and not response.json()["reviewed"]
    assert (
        client.post(f"/api/assistant/artifacts/{aid}/review", json={"revision": 1, "reviewed": True}).status_code == 409
    )
    assert client.get(f"/api/assistant/artifacts/{aid}/download").content.startswith(b"PK")
    with sessions() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "EDIT_ARTIFACT"))


def test_other_user_cannot_read_files_runs_or_edit(context):
    sessions, client = context
    cid, demo = setup_demo(client)
    request(client, cid, demo["prompt"], [a["id"] for a in demo["attachments"]])
    run_one(sessions)
    result = client.get("/api/assistant/conversations/" + cid).json()
    rid = result["runs"][0]["id"]
    aid = result["runs"][0]["artifacts"][0]["id"]
    with sessions() as db:
        db.add(User(username="other.hr", password_hash=hash_password("other-test-password")))
        db.commit()
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "other.hr", "password": "other-test-password"})
    assert client.get("/api/assistant/conversations/" + cid).status_code == 404
    assert client.get("/api/assistant/attachments/" + demo["attachments"][0]["id"] + "/download").status_code == 404
    assert client.get("/api/assistant/artifacts/" + aid + "/download").status_code == 404
    assert client.get("/api/assistant/runs/" + rid + "/download").status_code == 404
    assert (
        client.post("/api/assistant/artifacts/" + aid + "/review", json={"revision": 1, "reviewed": True}).status_code
        == 404
    )
    assert client.post("/api/assistant/conversations", headers={"Origin": "https://evil.example"}).status_code == 403


def test_worker_failure_retries_without_fake_results(context, monkeypatch):
    sessions, client = context
    cid, demo = setup_demo(client)
    request(client, cid, demo["prompt"], [a["id"] for a in demo["attachments"]])

    def fail(*args):
        raise AppError(503, "Model local chưa sẵn sàng.")

    monkeypatch.setattr("app.assistant.services.workflow.planner.create_plan", fail)
    run_one(sessions)
    with sessions() as db:
        job = db.scalar(select(ProcessingJob))
        assert job.status == "PENDING"
        job.available_at = utcnow()
        db.commit()
    run_one(sessions)
    with sessions() as db:
        assert db.scalar(select(ProcessingJob)).status == "FAILED"
        assert db.scalar(select(GenerationRun)).status == "FAILED"
        assert not list(db.scalars(select(Artifact)))


def test_real_csv_txt_upload_and_authentication(context):
    sessions, client = context
    cid = client.post("/api/assistant/conversations").json()["id"]
    ids = []
    for name, role, data in [
        ("mau.txt", "template", "Kính gửi {{Họ tên}} · {{Mã}}"),
        ("data.csv", "data", "Họ tên,Mã\nNguyễn A,NV001"),
    ]:
        response = client.post(
            f"/api/assistant/conversations/{cid}/attachments",
            data={"role": role},
            files={"file": (name, data.encode(), "application/octet-stream")},
        )
        assert response.status_code == 200, response.text
        ids.append(response.json()["id"])
    request(client, cid, "Điền hồ sơ theo mẫu cho tất cả bản ghi.", ids)
    run_one(sessions)
    assert len(client.get("/api/assistant/conversations/" + cid).json()["runs"][0]["artifacts"]) == 1
    client.post("/api/auth/logout")
    assert client.get("/api/assistant/conversations").status_code == 401


def test_generation_validation_error_does_not_commit_partial_artifacts(context, monkeypatch):
    from app.assistant.errors import InputError
    from app.assistant.services import documents

    sessions, client = context
    cid, demo = setup_demo(client)
    request(client, cid, demo["prompt"], [a["id"] for a in demo["attachments"]])
    actual = documents.render_template
    count = 0

    def render(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise InputError("Trường dữ liệu thứ hai chưa hợp lệ.")
        return actual(*args, **kwargs)

    monkeypatch.setattr(documents, "render_template", render)
    run_one(sessions)
    run = client.get("/api/assistant/conversations/" + cid).json()["runs"][0]
    assert run["status"] == "NEEDS_INPUT" and run["artifacts"] == []
