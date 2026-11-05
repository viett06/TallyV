import io
import uuid
import zipfile

import pytest
from docx import Document
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.assistant.errors import AppError, InputError
from app.assistant.models import GenerationRun, TaskStep
from app.assistant.schema.tasks import DataPlan, DataStep, MetricBinding
from app.assistant.services import datasets, orchestration, task_documents, task_planner, tasks, tools
from app.models import ProcessingJob, User
from app.services.security import hash_password
from app.worker import run_one


def sample_book():
    book = Workbook()
    sheet = book.active
    sheet.title = "Staff"
    for row in [
        ["ID", "Role", "Year"],
        ["001", "Cardiology physician", 2024],
        ["002", "Pediatric nurse", 2024],
        ["003", "Head of emergency department", 2024],
        ["001", "Cardiology physician", 2025],
        ["001", "Cardiology physician", 2025],
    ]:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def sample_template():
    document = Document()
    document.add_heading("Workforce report", 0)
    document.add_paragraph("Selected rows: {{total_rows}}")
    document.add_paragraph("{{summary_table}}")
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def sample_plan(source):
    return DataPlan(
        title="Classify and count source rows",
        steps=[
            DataStep(
                id="classified",
                tool="classify_values",
                inputs=[source],
                arguments={"column": "Role", "target_column": "Category", "categories": ["Physician", "Nurse"]},
            ),
            DataStep(
                id="counts",
                tool="aggregate_rows",
                inputs=["classified"],
                arguments={"group_by": ["Year", "Category"], "measures": [{"name": "Rows", "operation": "count_rows"}]},
            ),
        ],
        result="classified",
        summary="counts",
    )


def setup_task(context, monkeypatch, *, unknown=True):
    sessions, client = context
    cid = client.post("/api/assistant/conversations").json()["id"]
    ids = []
    for name, role, content in [
        ("Staff.xlsx", "data", sample_book()),
        ("Template.docx", "template", sample_template()),
    ]:
        response = client.post(
            f"/api/assistant/conversations/{cid}/attachments", data={"role": role}, files={"file": (name, content)}
        )
        assert response.status_code == 200, response.text
        ids.append(response.json()["id"])

    def plan(request, catalog, fields, rules, call):
        return sample_plan(catalog[0]["id"])

    monkeypatch.setattr("app.assistant.services.task_planner.create_plan", plan)
    # Explicit request rules are literal, authorized input, not a mocked arithmetic result.
    text = 'Classify and count rows by Year. "Cardiology physician" -> "Physician"; "Pediatric nurse" -> "Nurse".'
    if not unknown:
        text += ' "Head of emergency department" -> "Physician".'

    def planned(request, catalog, fields, rules, call):
        result = plan(request, catalog, fields, rules, call)
        result.steps[0].arguments["rules"] = {"Cardiology physician": "Physician", "Pediatric nurse": "Nurse"}
        if not unknown:
            result.steps[0].arguments["rules"]["Head of emergency department"] = "Physician"
        return result

    monkeypatch.setattr("app.assistant.services.task_planner.create_plan", planned)
    key = str(uuid.uuid4())
    body = {"text": text, "attachment_ids": ids, "request_key": key, "task_mode": "data"}
    response = client.post(f"/api/assistant/conversations/{cid}/messages", json=body)
    assert response.status_code == 202, response.text
    assert client.post(f"/api/assistant/conversations/{cid}/messages", json=body).json() == response.json()
    return sessions, client, cid, response.json()["run_id"]


def drain(sessions, max_steps=30):
    for _ in range(max_steps):
        if not run_one(sessions):
            return
    raise AssertionError("Task did not terminate within the tool budget")


def latest(client, cid):
    return client.get(f"/api/assistant/conversations/{cid}").json()["runs"][-1]


def test_classification_review_recounts_duplicate_rows_and_fills_word(context, monkeypatch):
    sessions, client, cid, run_id = setup_task(context, monkeypatch)
    drain(sessions)
    run = latest(client, cid)
    assert run["status"] == "NEEDS_INPUT", run
    assert run["task"]["issue_count"] == 1
    assert not run["artifacts"]
    assert "storage_key" not in str(run)
    body = {
        "revision": 1,
        "decisions": [
            {"step_id": "classified", "key": "Head of emergency department", "category": "Physician", "save_rule": True}
        ],
        "request_key": str(uuid.uuid4()),
    }
    revised = client.post(f"/api/assistant/conversations/{cid}/runs/{run_id}/revise", json=body)
    assert revised.status_code == 202, revised.text
    assert client.post(f"/api/assistant/conversations/{cid}/runs/{run_id}/revise", json=body).json() == revised.json()
    drain(sessions)
    run = latest(client, cid)
    assert run["status"] == "COMPLETED", run
    assert run["revision"] == 2 and run["parent_run_id"] == run_id
    result = client.get(f"/api/assistant/conversations/{cid}/runs/{run['id']}/dataset").json()
    counts = {(r["values"]["Year"], r["values"]["Category"]): r["values"]["Rows"] for r in result["rows"]}
    assert counts == {("2024", "Nurse"): 1, ("2024", "Physician"): 2, ("2025", "Physician"): 2}
    assert len(result["rows"][2]["lineage"]) == 2
    rules = client.get("/api/assistant/rules").json()
    assert len(rules) == 1 and rules[0]["source_value"] == "Head of emergency department"
    word = next(a for a in run["artifacts"] if a["name"].endswith(".docx"))
    output = client.get(f"/api/assistant/artifacts/{word['id']}/download")
    document = Document(io.BytesIO(output.content))
    assert "Selected rows: 5" in [p.text for p in document.paragraphs]
    assert len(document.tables[0].rows) == 4
    workbook = next(a for a in run["artifacts"] if a["name"].endswith(".xlsx"))
    output = client.get(f"/api/assistant/artifacts/{workbook['id']}/download")
    assert output.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    book = load_workbook(io.BytesIO(output.content))
    assert book["Details"].max_row == 6
    assert book["Details"]["A2"].value == "001"
    assert all(s["status"] == "COMPLETED" for s in run["steps"])
    assert (
        client.post(
            f"/api/assistant/conversations/{cid}/runs/{run['id']}/review", json={"revision": 2, "reviewed": True}
        ).status_code
        == 200
    )
    assert all(a["reviewed"] for a in latest(client, cid)["artifacts"])
    revise = client.post(
        f"/api/assistant/conversations/{cid}/runs/{run['id']}/revise",
        json={
            "revision": 2,
            "decisions": [{"step_id": "classified", "key": "Head of emergency department", "category": "Nurse"}],
        },
    )
    assert revise.status_code == 202
    old = client.get(f"/api/assistant/conversations/{cid}").json()["runs"][-2]
    assert not old["task"]["reviewed"] and all(not a["reviewed"] for a in old["artifacts"])
    drain(sessions)
    new = latest(client, cid)
    assert new["status"] == "COMPLETED", new
    assert (
        client.post(
            f"/api/assistant/conversations/{cid}/runs/{run['id']}/review", json={"revision": 2, "reviewed": True}
        ).status_code
        == 409
    )
    exported = client.get(f"/api/assistant/runs/{new['id']}/download")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert "Lineage.json" in archive.namelist()


def test_cold_retry_keeps_completed_step_and_cancellation_cannot_restart(context, monkeypatch):
    sessions, client, cid, run_id = setup_task(context, monkeypatch, unknown=False)
    assert run_one(sessions)  # Inspection committed independently of future model failures.
    with sessions() as db:
        receipt = db.scalar(select(TaskStep).where(TaskStep.run_id == run_id))
        assert receipt.status == "COMPLETED" and receipt.attempts == 1
    original = orchestration.execute_tool
    calls = []

    def fail_once(step, inputs, context):
        calls.append(step.id)
        if len(calls) == 1:
            raise AppError(503, "Model unavailable")
        return original(step, inputs, context)

    monkeypatch.setattr(orchestration, "execute_tool", fail_once)
    assert run_one(sessions)  # Plan
    assert run_one(sessions)  # Tool fails
    with sessions() as db:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.key == "assistant:" + run_id))
        from app.core.time import utcnow

        job.available_at = utcnow()
        db.commit()
    drain(sessions)
    assert latest(client, cid)["status"] == "COMPLETED"
    with sessions() as db:
        receipt = db.scalar(select(TaskStep).where(TaskStep.run_id == run_id, TaskStep.step_id == "$inspect"))
        assert receipt.attempts == 1
    sessions, client, cid, run_id = setup_task(context, monkeypatch)
    assert client.post(f"/api/assistant/conversations/{cid}/runs/{run_id}/cancel").status_code == 200
    drain(sessions)
    assert latest(client, cid)["status"] == "CANCELLED"


def test_data_tools_are_generic_and_preserve_lineage_and_numeric_accuracy():
    source = {
        "columns": ["Code", "Dept", "Amount"],
        "rows": [
            {"id": str(i), "values": {"Code": code, "Dept": dept, "Amount": amount}, "lineage": [{"row": i + 2}]}
            for i, (code, dept, amount) in enumerate([("001", "A", "0.1"), ("002", "A", "0.2"), ("003", "B", "5")])
        ],
        "issues": [],
        "checks": [],
    }
    step = DataStep(
        id="sum",
        tool="aggregate_rows",
        inputs=["source"],
        arguments={"group_by": ["Dept"], "measures": [{"name": "Total", "operation": "sum", "column": "Amount"}]},
    )
    result = orchestration.execute_tool(step, [source], {"request": "Sum Amount by Dept"})
    assert result["rows"][0]["values"]["Total"] == 0.3
    assert result["rows"][0]["lineage"] == [{"row": 2}, {"row": 3}]
    lookup = {
        "columns": ["Code", "Name"],
        "rows": [{"id": "r", "values": {"Code": "001", "Name": "Alpha"}, "lineage": [{"file": "lookup", "row": 2}]}],
        "issues": [],
        "checks": [],
    }
    step = DataStep(
        id="joined", tool="join_rows", inputs=["source", "lookup"], arguments={"left_on": "Code", "right_on": "Code"}
    )
    result = tools.execute(step, [source, lookup], {})
    assert len(result["rows"]) == 3 and result["rows"][0]["values"]["Name"] == "Alpha"
    assert result["checks"][-1]["unmatched_rows"] == 2
    lookup["rows"] *= 2
    with pytest.raises(InputError):
        tools.execute(step, [source, lookup], {})
    malicious = {
        "columns": ["Value"],
        "rows": [{"id": "m", "values": {"Value": '=HYPERLINK("https://example.com")'}, "lineage": []}],
    }
    output = datasets.workbook_bytes([("Output", malicious)])
    cell = load_workbook(io.BytesIO(output))["Output"]["A2"]
    assert cell.data_type == "s"


def test_task_permissions_cover_review_sources_and_rules(context, monkeypatch):
    sessions, client, cid, run_id = setup_task(context, monkeypatch)
    drain(sessions)
    response = client.post(
        f"/api/assistant/conversations/{cid}/runs/{run_id}/revise",
        json={
            "revision": 1,
            "decisions": [
                {
                    "step_id": "classified",
                    "key": "Head of emergency department",
                    "category": "Physician",
                    "save_rule": True,
                }
            ],
        },
    )
    assert response.status_code == 202
    rule_id = client.get("/api/assistant/rules").json()[0]["id"]
    with sessions() as db:
        db.add(User(username="other.data.hr", password_hash=hash_password("other-password")))
        db.commit()
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "other.data.hr", "password": "other-password"})
    base = f"/api/assistant/conversations/{cid}/runs/{run_id}"
    assert client.get(base + "/dataset").status_code == 404
    assert client.get(base + "/classifications").status_code == 404
    assert client.post(base + "/revise", json={"revision": 1, "text": "Continue"}).status_code == 404
    assert client.post(base + "/cancel").status_code == 404
    assert client.post(base + "/review", json={"revision": 1, "reviewed": True}).status_code == 404
    assert client.get("/api/assistant/rules").json() == []
    assert client.post(f"/api/assistant/rules/{rule_id}/retire", json={"version": 1}).status_code == 404


def test_xlsx_report_and_plain_word_bindings_are_verified():
    table = {
        "columns": ["Year", "Count"],
        "rows": [{"id": "x", "values": {"Year": "2025", "Count": 2}, "lineage": [{"row": 2}, {"row": 3}]}],
        "issues": [],
    }
    plan = DataPlan(
        result="counts",
        summary="counts",
        bindings={"count_2025": MetricBinding(dataset="counts", column="Count", where={"Year": "2025"})},
    )
    book = Workbook()
    book.active["A1"] = "Count: {{count_2025}}"
    book.active["A3"] = "{{summary_table}}"
    book.active["E2"] = "Keep original content"
    content = io.BytesIO()
    book.save(content)
    rendered, name, _, provenance = task_documents.render_report(
        {"name": "Template.xlsx"}, content.getvalue(), plan, {"counts": table}, 2
    )
    output = load_workbook(io.BytesIO(rendered)).active
    assert name.endswith(".xlsx") and output["A1"].value == "Count: 2"
    assert output["A3"].value == "Year" and output["B4"].value == 2
    assert output["E2"].value == "Keep original content"
    assert provenance["metrics"]["count_2025"] == 2
    from app.assistant.schema.planning import Rewrite
    from app.assistant.services import documents

    raw, paragraphs = documents.load_template("Template.txt", b"Count: ....")
    plan.rewrites = [Rewrite(paragraph_id=paragraphs[0]["id"], text="Count: {{count_2025}}")]
    rendered, _, _, _ = task_documents.render_report({"name": "Template.docx"}, raw, plan, {"counts": table}, 2)
    assert Document(io.BytesIO(rendered)).paragraphs[0].text == "Count: 2"
    plan.rewrites[0].text = "Change the fixed statement {{count_2025}}"
    with pytest.raises(InputError):
        task_documents.render_report({"name": "Template.docx"}, raw, plan, {"counts": table}, 2)


def test_validation_and_explicit_replacements_do_not_invent_source_values():
    data = {
        "columns": ["Year", "Amount"],
        "rows": [{"id": "a", "values": {"Year": "202x", "Amount": "N/A"}, "lineage": [{"row": 2}]}],
        "issues": [],
    }
    step = DataStep(
        id="checked",
        tool="validate_rows",
        inputs=["source"],
        arguments={"checks": [{"column": "Year", "kind": "year"}, {"column": "Amount", "kind": "numeric"}]},
    )
    output = tools.execute(step, [data], {})
    assert len(output["issues"]) == 2 and output["checks"][-1]["passed"] is False
    replace = DataStep(
        id="corrected",
        tool="replace_values",
        inputs=["source"],
        arguments={"column": "Year", "mapping": {"202x": "2025"}},
    )
    with pytest.raises(InputError):
        tools.execute(replace, [data], {"request": "Fix the year"})
    output = tools.execute(replace, [data], {"request": "Replace 202x with 2025"})
    assert output["rows"][0]["values"]["Year"] == "2025"
    assert data["rows"][0]["values"]["Year"] == "202x"


def test_plan_rejects_cross_source_references_and_unrequested_distinct_counts():
    plan = DataPlan(result="other-owner-file")
    with pytest.raises(InputError):
        task_planner.validate_plan(plan, ["source_1"], "Process rows")
    plan = DataPlan(
        steps=[
            DataStep(
                id="counted",
                tool="aggregate_rows",
                inputs=["source_1"],
                arguments={
                    "group_by": [],
                    "measures": [{"name": "Count", "operation": "count_distinct", "column": "ID"}],
                },
            )
        ],
        result="counted",
    )
    with pytest.raises(InputError):
        task_planner.validate_plan(plan, ["source_1"], "Count rows")
    assert task_planner.validate_plan(plan, ["source_1"], "Count distinct employee IDs")


def test_narrative_uses_metric_tokens_and_rejects_uncomputed_numbers():
    data = {
        "columns": ["Year", "Count"],
        "rows": [{"id": "r", "values": {"Year": "2025", "Count": 3}, "lineage": [{"row": 2}]}],
        "issues": [],
    }
    step = DataStep(
        id="narrative", tool="write_narrative", inputs=["counts"], arguments={"topic": "Describe the computed table"}
    )

    def grounded(schema, instruction, payload):
        return tools.NarrativeReply(text="Year [[m0]] has [[m1]] source rows.")

    output = tools.execute(step, [data], {"use_model": True, "model_call": grounded})
    assert output["rows"][0]["values"]["Narrative"] == "Year 2025 has 3 source rows."

    def invented(schema, instruction, payload):
        return tools.NarrativeReply(text="There are 999 employees.")

    with pytest.raises(InputError):
        tools.execute(step, [data], {"use_model": True, "model_call": invented})


def test_model_calls_release_database_and_enforce_a_durable_budget(context, monkeypatch):
    sessions, client, cid, run_id = setup_task(context, monkeypatch)
    from app.assistant.config import settings

    monkeypatch.setattr(settings, "max_model_calls", 1)
    with sessions() as db:

        def reply(schema, instruction, data, output_schema=None, **options):
            assert not db.in_transaction()
            return DataPlan(question="Clarify the source")

        monkeypatch.setattr("app.assistant.services.planner.schema_call", reply)
        caller = tasks.model_caller(db, run_id)
        caller(DataPlan, "Plan", {})
        with pytest.raises(InputError):
            caller(DataPlan, "Plan", {})
        assert db.get(GenerationRun, run_id).state["model_calls"] == 1


def test_cancel_while_a_tool_is_running_cannot_publish_results(context, monkeypatch):
    sessions, client, cid, run_id = setup_task(context, monkeypatch, unknown=False)
    original = orchestration.execute_tool

    def cancel_during_execution(step, inputs, tool_context):
        assert client.post(f"/api/assistant/conversations/{cid}/runs/{run_id}/cancel").status_code == 200
        return original(step, inputs, tool_context)

    monkeypatch.setattr(orchestration, "execute_tool", cancel_during_execution)
    drain(sessions)
    result = latest(client, cid)
    assert result["status"] == "CANCELLED" and not result["artifacts"]


def test_staged_planning_binds_typed_outputs_and_exact_grouping(monkeypatch):
    from app.assistant.config import settings

    monkeypatch.setattr(settings, "processing_mode", "LOCAL_LLM")
    source = {
        "columns": ["Role", "Year", "Category", "Review status"],
        "rows": [
            {
                "id": "r",
                "values": {"Role": "Head", "Year": "2025", "Category": "Physician", "Review status": "Confirmed"},
                "lineage": [],
            }
        ],
        "review_columns": ["Review status"],
    }
    outline = DataPlan(
        steps=[
            DataStep(id="step_1", tool="classify_values", inputs=["source_1"]),
            DataStep(id="step_2", tool="aggregate_rows", inputs=["step_1"]),
        ]
    )
    task_planner.compile_outputs(outline, ["source_1"])
    assert (outline.result, outline.summary) == ("step_1", "step_2")
    outline.steps[0].arguments = {"column": "Role", "target_column": "Category", "categories": ["Physician", "Nurse"]}

    def configure(schema, instruction, payload, output_schema):
        assert "Review status" not in payload["inputs"][0]["columns"]
        assert output_schema["properties"]["group_by"]["enum"] == [["Year", "Category"]]
        return tools.AggregateArgs(
            group_by=["Year", "Category"], measures=[tools.Measure(name="Rows", operation="count_rows")]
        )

    arguments = task_planner.prepare_arguments(
        outline.steps[1], [source], "Classify roles, count rows by Year and Category", [], configure
    )
    assert arguments["group_by"] == ["Year", "Category"]
    outline.steps[1].arguments = arguments
    assert task_planner.validate_plan(outline, ["source_1"], "Classify roles, count rows by Year and Category")
    outline.steps[1].inputs = ["source_1"]
    with pytest.raises(InputError):
        task_planner.validate_plan(outline, ["source_1"], "Classify roles, count rows by Year and Category")


def test_classification_rules_require_actual_mapping_not_keyword_cooccurrence():
    assert tools.explicit_mapping('"Cardiology physician" -> "Physician"', "Cardiology physician", "Physician")
    assert not tools.explicit_mapping(
        'Classify "Cardiology physician" into "Nurse" or "Physician"', "Cardiology physician", "Nurse"
    )


def test_numeric_sort_does_not_order_totals_lexicographically():
    source = {
        "columns": ["Count"],
        "rows": [
            {"id": str(index), "values": {"Count": value}, "lineage": []} for index, value in enumerate([10, 2, 100])
        ],
        "issues": [],
    }
    step = DataStep(id="sorted", tool="sort_rows", inputs=["source"], arguments={"columns": ["Count"]})
    result = tools.execute(step, [source], {})
    assert [row["values"]["Count"] for row in result["rows"]] == [2, 10, 100]


def test_plain_report_blanks_keep_fixed_wording_and_require_computed_bindings():
    from app.assistant.schema.tasks import ReportSelection
    from app.assistant.services import documents

    content, _ = documents.load_template("Report.txt", b"Selected rows: ....")
    template = task_documents.inspect_template({"id": "template", "name": "Report.docx"}, content)
    field = template["fields"][0]
    data = {"columns": ["ID"], "rows": [{"id": "a", "values": {"ID": "001"}, "lineage": []}], "issues": []}
    plan = DataPlan(result="detail")

    def bind(schema, instruction, payload, output_schema):
        assert "normalized_rewrites" not in payload["template"]
        assert output_schema["properties"]["bindings"]["required"] == [field]
        assert output_schema["properties"]["rewrites"]["maxItems"] == 0
        return ReportSelection(bindings={field: payload["available_metrics"][0]["id"]})

    report = task_planner.prepare_report(plan, template, {"detail": data}, "Complete the row count", bind)
    plan.bindings, plan.tables, plan.rewrites = report.bindings, report.tables, report.rewrites
    output, _, _, _ = task_documents.render_report({"name": "Report.docx"}, content, plan, {"detail": data}, 1)
    assert Document(io.BytesIO(output)).paragraphs[0].text == "Selected rows: 1"
