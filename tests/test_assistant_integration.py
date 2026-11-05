import importlib.util
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text

from app.assistant.models import Conversation
from app.db.base_model import Base
from app.models import ProcessingJob
from app.worker import run_one
from tests.test_assistant_workflow import request, setup_demo


def test_assistant_uses_tallyv_session_queue_and_private_job_controls(context):
    sessions, client = context
    assert client.cookies.get("tallyv_session")
    assert not client.cookies.get("draftv_session")
    assert client.get("/api/assistant/capabilities").status_code == 200
    cid, demo = setup_demo(client)
    result = request(client, cid, demo["prompt"], [a["id"] for a in demo["attachments"]])
    with sessions() as db:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "ASSISTANT_GENERATE"))
        assert job.key == "assistant:" + result["run_id"]
        assert job.payload == {"run_id": result["run_id"]}
        assert job.max_attempts == 2
        job_id = job.id
        assert db.get(Conversation, cid).user_id is not None
    assert job_id not in [job["id"] for job in client.get("/api/jobs").json()]
    assert client.post(f"/api/jobs/{job_id}/retry").status_code == 404
    assert run_one(sessions)
    assert client.get(f"/api/assistant/conversations/{cid}").json()["runs"][0]["status"] == "COMPLETED"
    assert client.get("/api/bootstrap").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/assistant/capabilities").status_code == 401
    assert client.get("/api/assistant/conversations").status_code == 401


def test_assistant_rejects_oversized_requests_before_parsing_upload(context):
    _, client = context
    response = client.post(
        "/api/assistant/conversations/unused/attachments",
        headers={"Content-Length": str(16 * 1024 * 1024)},
    )
    assert response.status_code == 413


def test_assistant_migration_is_additive_and_matches_models(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/a368e7c015b2_add_assistant_module.py"
    spec = importlib.util.spec_from_file_location("assistant_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    task_path = path.parent / "b479f8d126c3_assistant_data_tasks.py"
    task_spec = importlib.util.spec_from_file_location("assistant_task_migration", task_path)
    task_migration = importlib.util.module_from_spec(task_spec)
    task_spec.loader.exec_module(task_migration)
    engine = create_engine("sqlite://")
    original_tables = [table for table in Base.metadata.sorted_tables if not table.name.startswith("assistant_")]
    with engine.begin() as db:
        Base.metadata.create_all(db, tables=original_tables)
        db.execute(
            text("INSERT INTO users (id, username, password_hash, role) VALUES (1, 'existing.hr', 'keep-hash', 'HR')")
        )
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(db)))
        monkeypatch.setattr(task_migration, "op", Operations(MigrationContext.configure(db)))
        migration.upgrade()
        task_migration.upgrade()
        assert len([name for name in inspect(db).get_table_names() if name.startswith("assistant_")]) == 8
        assert not compare_metadata(MigrationContext.configure(db), Base.metadata)
        assert db.scalar(text("SELECT password_hash FROM users WHERE id = 1")) == "keep-hash"
        task_migration.downgrade()
        migration.downgrade()
        assert set(inspect(db).get_table_names()) == {table.name for table in original_tables}
        assert db.scalar(text("SELECT username FROM users WHERE id = 1")) == "existing.hr"
    engine.dispose()
