"""Run the real local model against synthetic files in an isolated database and file store."""

import argparse
import io
import tempfile
import time
import uuid
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.assistant.config import settings as assistant_settings
from app.assistant.services import planner
from app.core.config import settings
from app.db.base_model import Base
from app.db.session import get_session
from app.models import User
from app.services.security import hash_password
from app.worker import run_one
from main import app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Print model responses for synthetic inputs only")
    parser.add_argument(
        "--plain-report", action="store_true", help="Also verify mapping a plain Word blank to a computed metric"
    )
    options = parser.parse_args()
    verbose = options.verbose
    original_call = planner.schema_call
    if verbose:

        def observed_call(schema, *args, **kwargs):
            started = time.monotonic()
            result = original_call(schema, *args, **kwargs)
            print(schema.__name__, round(time.monotonic() - started, 2), result.model_dump(), flush=True)
            return result

        planner.schema_call = observed_call
    assistant_settings.processing_mode = "LOCAL_LLM"
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    password = str(uuid.uuid4())
    with sessions() as db:
        db.add(User(username="assistant.synthetic.check", password_hash=hash_password(password)))
        db.commit()

    def dependency():
        with sessions() as db:
            yield db

    with tempfile.TemporaryDirectory(prefix="tallyv-assistant-check-") as directory:
        settings.storage_backend, settings.storage_dir = "local", Path(directory)
        app.dependency_overrides[get_session] = dependency
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/auth/login", json={"username": "assistant.synthetic.check", "password": password}
                )
                response.raise_for_status()
                cid = client.post("/api/assistant/conversations").json()["id"]
                demo = client.post(f"/api/assistant/conversations/{cid}/demo-data").json()
                if options.plain_report:
                    document = Document()
                    document.add_paragraph("Selected rows: ....")
                    document.add_paragraph("{{summary_table}}")
                    stream = io.BytesIO()
                    document.save(stream)
                    uploaded = client.post(
                        f"/api/assistant/conversations/{cid}/attachments",
                        data={"role": "template"},
                        files={"file": ("Plain_report.docx", stream.getvalue())},
                    )
                    uploaded.raise_for_status()
                    demo["attachments"] = [item for item in demo["attachments"] if item["role"] == "data"] + [
                        uploaded.json()
                    ]
                    demo["prompt"] += (
                        " Fill the blank after Selected rows with the total number of detail rows, keeping the wording unchanged."
                    )
                response = client.post(
                    f"/api/assistant/conversations/{cid}/messages",
                    json={
                        "text": demo["prompt"],
                        "attachment_ids": [item["id"] for item in demo["attachments"]],
                        "request_key": str(uuid.uuid4()),
                        "task_mode": "data",
                    },
                )
                response.raise_for_status()
                previous = ""
                for _ in range(60):
                    worked = run_one(sessions)
                    run = client.get(f"/api/assistant/conversations/{cid}").json()["runs"][-1]
                    phase = str(run["task"].get("phase")) + ":" + run["status"]
                    if phase != previous:
                        print(phase, flush=True)
                        previous = phase
                    if run["status"] == "NEEDS_INPUT":
                        pending = client.get(
                            f"/api/assistant/conversations/{cid}/runs/{run['id']}/classifications"
                        ).json()["rows"]
                        expected = {
                            "Cardiology physician": "Physician",
                            "Pediatric nurse": "Nurse",
                            "Head of emergency department": "Physician",
                            "Pharmacist": "Pharmacist",
                        }
                        decisions = [
                            {"step_id": item["step_id"], "key": item["key"], "category": expected[item["label"]]}
                            for item in pending
                            if item["label"] in expected
                            and expected[item["label"]] in item["categories"]
                            and (item.get("method") == "model" or item["category"] is None)
                        ]
                        if not decisions:
                            raise RuntimeError(
                                "Real-model clarification requires inspection: "
                                + run["summary"]
                                + "\n"
                                + str(run["plan"])
                            )
                        response = client.post(
                            f"/api/assistant/conversations/{cid}/runs/{run['id']}/revise",
                            json={"revision": run["revision"], "decisions": decisions},
                        )
                        response.raise_for_status()
                        continue
                    if run["status"] == "COMPLETED":
                        assert len(run["artifacts"]) == 2
                        summary = client.get(f"/api/assistant/conversations/{cid}/runs/{run['id']}/dataset").json()
                        assert summary["total"] > 0
                        assert run["task"]["validation"]["detail_rows"] == 8
                        category_column = next(
                            step["arguments"]["target_column"]
                            for step in run["plan"]["steps"]
                            if step["tool"] == "classify_values"
                        )
                        count_column = next(
                            metric["name"]
                            for step in run["plan"]["steps"]
                            if step["tool"] == "aggregate_rows"
                            for metric in step["arguments"]["measures"]
                            if metric["operation"] == "count_rows"
                        )
                        actual = {
                            (str(row["values"]["Year"]), row["values"][category_column]): row["values"][count_column]
                            for row in summary["rows"]
                        }
                        assert actual == {
                            ("2024", "Physician"): 2,
                            ("2024", "Nurse"): 1,
                            ("2025", "Physician"): 2,
                            ("2025", "Nurse"): 1,
                            ("2025", "Pharmacist"): 1,
                            ("2026", "Physician"): 1,
                        }, actual
                        report = next(item for item in run["artifacts"] if item["name"].endswith(".docx"))
                        response = client.get(f"/api/assistant/artifacts/{report['id']}/download")
                        document = Document(io.BytesIO(response.content))
                        assert len(document.tables) >= 1
                        assert all("{{" not in paragraph.text for paragraph in document.paragraphs)
                        if options.plain_report:
                            assert "Selected rows: 8" in [paragraph.text for paragraph in document.paragraphs], (
                                [paragraph.text for paragraph in document.paragraphs],
                                run["plan"]["bindings"],
                            )
                        print(
                            "PASS: real model planned; tools executed; HR review resumed; Excel and Word rendered.",
                            flush=True,
                        )
                        return
                    if not worked:
                        if run.get("job", {}).get("status") == "PENDING":
                            time.sleep(1)
                            continue
                        raise RuntimeError("Worker stopped before completion: " + run["summary"])
                raise RuntimeError("Task exceeded the verification budget")
        finally:
            planner.schema_call = original_call
            app.dependency_overrides.clear()
            engine.dispose()


if __name__ == "__main__":
    main()
