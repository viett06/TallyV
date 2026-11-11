import io
import json
import os
from functools import partial
from types import SimpleNamespace

import httpx
import pytest
from docx import Document
from openpyxl import Workbook
from pydantic import SecretStr

from app.assistant.config import settings
from app.assistant.schema.tasks import DataPlan, DataStep
from app.assistant.services import hybrid, hybrid_codegen, hybrid_sandbox, planner, tools
from app.core.config import settings as app_settings
from app.worker import run_one
from scripts.assistant_sandbox import docker_command, run_in_sandbox

SECRET = "PRIVATE_MARKER_DO_NOT_SEND"


def workbook():
    book = Workbook()
    for i in range(10):
        sheet = book.active if i == 0 else book.create_sheet()
        sheet.title = f"{SECRET}_{i}"
        sheet.append(["Khoa", "Lương", *[f"{SECRET}_COL{col}" for col in range(28)]])
        sheet.append([SECRET, 125_070, *["ghi chú"] * 28])
        sheet.append([SECRET, 240_000, *["ghi chú"] * 28])
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def template():
    doc = Document()
    doc.add_paragraph(f"Báo cáo {SECRET}")
    doc.add_paragraph("Dòng nguồn: {{total_rows}}")
    doc.add_paragraph("{{summary_table}}")
    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()


@pytest.mark.parametrize("always_wrong", [False, True])
def test_hybrid_workbook_checkpoint_privacy_repair_and_report(context, monkeypatch, always_wrong):
    sessions, client = context
    monkeypatch.setattr(settings, "processing_mode", "HYBRID")
    monkeypatch.setattr(settings, "sandbox_url", "http://127.0.0.1:8100")
    monkeypatch.setattr(settings, "sandbox_token", SecretStr("synthetic-test-token-32-characters"))
    monkeypatch.setattr(app_settings, "openrouter_api_key", SecretStr("synthetic-test-api-key"))
    sheets, outgoing = [], []

    def local(schema, _instruction, data, _output_schema=None, **kwargs):
        assert kwargs["model"] == "qwen3.5:4b-q4_K_M"
        if schema is hybrid_codegen.SheetDescription:
            assert SECRET in data["file"] and SECRET in data["sheet"]
            assert len(data["columns"]) == 30 and data["columns"][1]["type"] == "integer"
            sheets.append(data["sheet"])
            return schema(
                meaning="payroll",
                description=SECRET,
                columns=[
                    {"index": index, "meaning": "amount" if index == 2 else "other", "description": SECRET}
                    for index in range(1, 31)
                ],
            )
        if schema is DataPlan:
            assert len(data["source_catalog"]) == 10
            assert SECRET in data["request"]
            return DataPlan(steps=[DataStep(id=SECRET, tool="aggregate_rows", inputs=["source_1"])])
        assert schema.__name__ == "HybridToolConfiguration"
        return schema(
            question=None,
            arguments=tools.AggregateArgs(
                group_by=["Khoa"],
                measures=[tools.Measure(name="Tổng", operation="sum", column="Lương")],
            ),
        )

    def respond(request):
        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        payload = json.loads(request.content)
        assert SECRET.encode() not in request.content
        assert b"125070" not in request.content and b"365070" not in request.content
        assert payload["provider"]["zdr"] and payload["model"] == "openai/gpt-5.4-mini"
        assert payload["provider"]["only"] == ["azure"]
        data = json.loads(payload["messages"][1]["content"])
        outgoing.append(data)
        assert len(data["sheets"]) == 1 and len(data["sheets"][0]["columns"]) == 30
        script = "def transform(sources, steps, outputs):\n    return {}\n"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps({"code": script})},
                    }
                ]
            },
        )

    sandbox_inputs = []

    def isolated(request):
        sandbox_inputs.append(request)
        assert request.sources["source_1"]["rows"][0]["Khoa"] == SECRET
        # Simulate the isolated runner reporting a script that ran but gave a wrong total.
        total = 125070 if always_wrong or len(sandbox_inputs) == 1 else 365070
        return hybrid_sandbox.ExecutionResult(
            result={
                "source_1": request.sources["source_1"],
                "step_1": {"columns": ["Khoa", "Tổng"], "rows": [{"Khoa": SECRET, "Tổng": total}]},
            }
        )

    monkeypatch.setattr(planner, "schema_call", local)
    monkeypatch.setattr(hybrid_sandbox, "execute", isolated)
    monkeypatch.setattr(
        hybrid_codegen,
        "httpx",
        SimpleNamespace(
            Client=partial(httpx.Client, transport=httpx.MockTransport(respond)),
            HTTPError=httpx.HTTPError,
        ),
    )
    cid = client.post("/api/assistant/conversations").json()["id"]
    base = f"/api/assistant/conversations/{cid}"
    ids = []
    for role, name, content in [
        ("data", f"{SECRET}.xlsx", workbook()),
        ("template", "report.docx", template()),
    ]:
        response = client.post(base + "/attachments", data={"role": role}, files={"file": (name, content)})
        assert response.status_code < 300, response.text
        ids.append(response.json()["id"])
    response = client.post(
        base + "/messages",
        json={
            "text": f"Tổng hợp lương theo khoa. {SECRET}",
            "attachment_ids": ids,
            "request_key": "hybrid-test-workbook-10-sheets",
        },
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]

    for _ in range(35):
        assert run_one(sessions)
        run = client.get(base).json()["runs"][-1]
        if run["status"] in {"COMPLETED", "NEEDS_INPUT"}:
            break
        assert run["status"] in {"RUNNING", "QUEUED"}, run
        assert not run["artifacts"]
        assert client.get(f"{base}/runs/{run_id}/dataset").status_code == 404
        assert client.get(f"/api/assistant/runs/{run_id}/download?kind=csv").status_code == 409
    assert len(sheets) == len(set(sheets)) == 10
    if always_wrong:
        assert run["status"] == "NEEDS_INPUT", run
        assert [request["repair"] for request in outgoing] == [None, "WRONG_ROWS", "WRONG_ROWS"]
        assert not run["artifacts"]
        return
    assert run["status"] == "COMPLETED", run
    assert run["task"]["validation"]["script_replay_verified"]
    assert [request["repair"] for request in outgoing] == [None, "WRONG_ROWS"]
    assert outgoing[1]["failed_output"] == "step_1"
    report = next(item for item in run["artifacts"] if item["name"] == "Report.docx")
    result = client.get(f"/api/assistant/artifacts/{report['id']}/download")
    document = Document(io.BytesIO(result.content))
    assert any(p.text == "Dòng nguồn: 2" for p in document.paragraphs)
    assert document.tables[0].cell(1, 1).text == "365070"



def test_openrouter_sheet_profile_only_sends_header_names_and_types(monkeypatch):
    monkeypatch.setattr(settings, "hybrid_sheet_provider", "openrouter")
    monkeypatch.setattr(app_settings, "openrouter_api_key", SecretStr("synthetic-test-api-key"))

    def reject_local(*args, **kwargs):
        pytest.fail("Sheet profiling should use OpenRouter")

    def respond(request):
        body = json.loads(request.content)
        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        assert body["provider"]["zdr"] and body["provider"]["only"] == ["azure"]
        assert body["response_format"]["json_schema"]["name"] == "assistant_sheet_profile"
        assert SECRET not in request.content.decode()
        assert json.loads(body["messages"][1]["content"]) == {
            "columns": [{"index": 1, "name": "Trình độ", "type": "text"}],
        }
        description = {
            "meaning": "employees",
            "description": "Thông tin nhân sự",
            "columns": [{"index": 1, "meaning": "category", "description": "Trình độ chuyên môn"}],
        }
        return httpx.Response(200, json={"choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(description)}},
        ]})

    monkeypatch.setattr(planner, "schema_call", reject_local)
    monkeypatch.setattr(
        hybrid_codegen,
        "httpx",
        SimpleNamespace(Client=partial(httpx.Client, transport=httpx.MockTransport(respond)), HTTPError=httpx.HTTPError),
    )
    profile = hybrid.source_profile({
        "name": SECRET, "sheet": SECRET, "rows": [SECRET], "columns": ["Trình độ"], "types": ["text"],
    })
    assert profile["column_descriptions"][0]["meaning"] == "category"


def test_sandbox_launch_is_fail_closed_and_does_not_mount_host_paths():
    command = docker_command("test", "python:3.11-slim")
    assert {"--runtime=runsc", "--network=none", "--read-only", "--pull=never", "--log-driver=none"} <= set(command)
    assert not any(arg.startswith(("--volume", "--mount", "--env", "--privileged")) for arg in command)


@pytest.mark.skipif(os.environ.get("ASSISTANT_RUN_SANDBOX_TEST") != "1", reason="requires a Linux gVisor runner")
def test_real_sandbox_uses_no_network_or_credentials():
    request = hybrid_sandbox.ExecutionRequest(
        code="""import os, socket
def transform(sources, steps, outputs):
    assert not os.path.exists("/var/run/docker.sock")
    assert "OPENROUTER_API_KEY" not in os.environ and "ASSISTANT_SANDBOX_TOKEN" not in os.environ
    with socket.socket() as connection:
        connection.settimeout(1)
        assert connection.connect_ex(("192.0.2.1", 443)) != 0
    return {key: sources[key] for key in outputs}
""",
        sources={"source_1": {"columns": ["amount"], "rows": [{"amount": 123}]}},
        steps=[],
        outputs=["source_1"],
        timeout=20,
    )
    result = run_in_sandbox(request.model_dump_json().encode(), request.timeout)
    assert result.error is None and result.result == request.sources
