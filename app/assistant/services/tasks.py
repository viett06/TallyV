"""Durable data tasks with short transactions, typed plans, review and exact provenance."""

import copy
import time

from app.assistant.config import settings
from app.assistant.crud import conversations as crud
from app.assistant.crud import tasks as queries
from app.assistant.errors import AppError, InputError
from app.assistant.models import Artifact, AuditLog, BusinessRule, GenerationRun, Message, TaskStep
from app.assistant.schema.tasks import DataPlan
from app.assistant.services import datasets, orchestration, planner, task_documents, task_planner
from app.assistant.services.storage import read_bytes, store_bytes
from app.core.i18n import message
from app.core.time import utcnow
from app.crud.jobs import enqueue


def rule_view(rule):
    return {
        key: getattr(rule, key)
        for key in ("id", "source_column", "source_value", "category", "categories", "status", "version")
    }


def step_view(step):
    return {
        "id": step.step_id,
        "tool": step.tool,
        "status": step.status,
        "attempts": step.attempts,
        "elapsed_ms": step.elapsed_ms,
        "error": step.error,
    }


def require_run(db, conversation_id, run_id, user, *, lock=True):
    from app.assistant.services.conversations import require_conversation

    require_conversation(db, conversation_id, user.id, lock=lock)
    run = crud.run(db, run_id)
    if not run or run.conversation_id != conversation_id or run.kind != "DATA_TASK":
        raise AppError(404, message("assistant.data.task_not_found"))
    return run


def read_source(item):
    return {key: getattr(item, key) for key in ("id", "name", "role", "storage_key", "sha256")}


def model_caller(db, run_id):
    def call(schema, instruction, data, output_schema=None):
        # Persist consumption BEFORE the call. A timeout must not reset the budget.
        run = crud.run(db, run_id)
        db.refresh(run)
        if run.status == "CANCELLED":
            raise InputError(message("assistant.data.cancelled"))
        state = dict(run.state)
        calls = state.get("model_calls", 0)
        if calls >= settings.max_model_calls:
            raise InputError(message("assistant.data.model_budget"))
        state["model_calls"] = calls + 1
        run.state = state
        db.commit()
        return planner.schema_call(schema, instruction, data, output_schema, bounded=True)

    return call


def complete_step(db, run, step, output, elapsed):
    if run.status == "CANCELLED":
        return
    step.status, step.error, step.output = "COMPLETED", "", output
    step.elapsed_ms = int(elapsed * 1000)
    step.updated_at = utcnow()
    state = dict(run.state)
    state["elapsed_seconds"] = state.get("elapsed_seconds", 0) + elapsed
    run.state = state
    db.add(
        AuditLog(
            conversation_id=run.conversation_id,
            actor="worker",
            action="TASK_STEP",
            details={"run_id": run.id, "step_id": step.step_id, "tool": step.tool, "elapsed_ms": step.elapsed_ms},
        )
    )
    db.commit()


def pause(db, run, text, issues=None):
    run.status, run.summary = "NEEDS_INPUT", text
    state = dict(run.state)
    if issues is not None:
        state["issues"] = issues
    run.state = state
    db.add(
        Message(
            conversation_id=run.conversation_id,
            role="assistant",
            content=text,
            details={"run_id": run.id, "kind": "task_input"},
        )
    )


def advance(db, job):
    """Execute at most one durable phase; release the queue between successful phases."""
    run = crud.run(db, job.payload["run_id"])
    if run.status in {"CANCELLED", "COMPLETED", "NEEDS_INPUT"}:
        return True
    state = dict(run.state)
    if state.get("elapsed_seconds", 0) > settings.max_task_seconds:
        pause(db, run, message("assistant.data.time_budget"))
        return True
    receipts = {s.step_id: s for s in queries.steps(db, run.id)}
    if "$inspect" not in receipts or receipts["$inspect"].status != "COMPLETED":
        phase, tool, arguments = "$inspect", "inspect_sources", {}
    elif not run.plan or run.plan.get("question"):
        phase, tool, arguments = "$plan", "create_plan", {}
    else:
        plan = DataPlan.model_validate(run.plan)
        pending = next((s for s in plan.steps if s.id not in receipts or receipts[s.id].status != "COMPLETED"), None)
        template = run.source_snapshot.get("template")
        needs_report = template and (
            not template["fields"]
            and not plan.rewrites
            or set(template["fields"])
            - {"total_rows", "source_rows", "summary_table"}
            - set(plan.bindings)
            - set(plan.tables)
        )
        if pending and not pending.arguments:
            phase, tool, arguments = pending.id + "__configure", "configure_step", pending.model_dump()
        elif pending:
            phase, tool, arguments = pending.id, pending.tool, pending.model_dump()
        elif needs_report and not state.get("report_configured"):
            phase, tool, arguments = "$report", "bind_report", {}
        elif "$validate" not in receipts or receipts["$validate"].status != "COMPLETED":
            phase, tool, arguments = "$validate", "validate_results", {}
        else:
            phase, tool, arguments = "$render", "render_outputs", {}
    step = receipts.get(phase)
    if not step:
        step = TaskStep(run_id=run.id, step_id=phase, tool=tool)
        db.add(step)
    step.status, step.error = "RUNNING", ""
    step.attempts = (step.attempts or 0) + 1
    state["phase"] = phase
    run.state = state
    run.status = "RUNNING"
    items = [crud.attachment(db, aid) for aid in run.attachment_ids]
    if any(item is None or item.conversation_id != run.conversation_id for item in items):
        raise InputError(message("assistant.data.source_missing"))
    sources = [read_source(item) for item in items]
    source_metadata = [{k: item[k] for k in ("id", "name", "role", "sha256")} for item in sources]
    conversation = crud.conversation(db, run.conversation_id)
    owner_id = conversation.user_id
    if "rules" not in state:
        state["rules"] = [rule_view(r) for r in queries.rules(db, owner_id)]
        run.state = state
    input_hash = datasets.digest(
        {
            "phase": phase,
            "arguments": arguments,
            "sources": source_metadata,
            "refs": state.get("datasets", {}),
            "rules": state.get("rules", []),
            "decisions": state.get("decisions", {}),
        }
    )
    step.input_hash = input_hash
    # Network/model/file work happens without an open SQL transaction.
    db.commit()
    started = time.monotonic()
    try:
        if phase == "$inspect":
            catalog, references = [], {}
            total = 0
            template = None
            for source in sources:
                content = read_bytes(source["storage_key"], source["sha256"])
                if source["role"] == "template":
                    template = task_documents.inspect_template(source, content)
                    continue
                for _, data in datasets.source_datasets(source, content).items():
                    total += len(data["rows"])
                    if total > settings.max_data_rows:
                        raise InputError(message("assistant.data.row_limit", limit=settings.max_data_rows))
                    alias = f"source_{len(catalog) + 1}"
                    entry = datasets.profile(alias, data)
                    entry["name"] = source["name"]
                    entry["sheet"] = data["rows"][0]["lineage"][0].get("sheet", "")
                    catalog.append(entry)
                    references[alias] = datasets.save_snapshot(data)
            db.refresh(run)
            if run.status == "CANCELLED":
                return True
            run.source_snapshot = {"sources": source_metadata, "source_rows": total, "template": template}
            run.state = {**run.state, "catalog": catalog, "datasets": references}
            output = {"source_count": len(catalog), "rows": total}
        elif phase == "$plan":
            supplied = run.state.get("supplied_plan")
            if supplied:
                plan = task_planner.validate_plan(
                    DataPlan.model_validate(supplied),
                    [c["id"] for c in state["catalog"]],
                    run.request,
                    allow_unbound=True,
                )
            else:
                plan = task_planner.create_plan(
                    run.request,
                    state["catalog"],
                    run.source_snapshot.get("template") or {},
                    state.get("rules", []),
                    model_caller(db, run.id),
                )
            db.refresh(run)
            if run.status == "CANCELLED":
                return True
            run.plan = plan.model_dump()
            if plan.question:
                pause(db, run, plan.question)
            output = {"steps": len(plan.steps), "question": plan.question}
        elif phase.endswith("__configure"):
            plan = DataPlan.model_validate(run.plan)
            operation = next(s for s in plan.steps if s.id + "__configure" == phase)
            inputs = [datasets.load_snapshot(state["datasets"][ref]) for ref in operation.inputs]
            operation.arguments = task_planner.prepare_arguments(
                operation,
                inputs,
                run.request,
                state.get("rules", []),
                model_caller(db, run.id),
                lambda: task_planner.validate_plan(
                    plan, [c["id"] for c in state["catalog"]], run.request, allow_unbound=True
                ),
            )
            db.refresh(run)
            if run.status == "CANCELLED":
                return True
            run.plan = plan.model_dump()
            output = {"configured": operation.id}
        elif phase == "$report":
            plan = DataPlan.model_validate(run.plan)
            snapshots = {key: datasets.load_snapshot(ref) for key, ref in state["datasets"].items()}
            report = task_planner.prepare_report(
                plan, run.source_snapshot["template"], snapshots, run.request, model_caller(db, run.id)
            )
            db.refresh(run)
            if run.status == "CANCELLED":
                return True
            if report.question:
                pause(db, run, report.question)
            else:
                plan.bindings, plan.tables, plan.rewrites = report.bindings, report.tables, report.rewrites
                run.plan = plan.model_dump()
                run.state = {**run.state, "report_configured": True}
            output = {"bindings": len(report.bindings), "tables": len(report.tables)}
        elif phase == "$validate":
            plan = DataPlan.model_validate(run.plan)
            task_planner.validate_plan(plan, [c["id"] for c in state["catalog"]], run.request)
            output = validate_results(run, plan)
            db.refresh(run)
            if run.status == "CANCELLED":
                return True
            run.state = {**run.state, "validation": output, "issues": []}
        elif phase == "$render":
            plan = DataPlan.model_validate(run.plan)
            rendered = render_outputs(run, plan, sources)
            db.refresh(run)
            if run.status == "CANCELLED":
                return True
            # Remove only artifacts belonging to this unfinished render attempt.
            if not crud.list_artifacts(db, run.id):
                for metadata in rendered:
                    db.add(Artifact(run_id=run.id, **metadata))
            run.status = "COMPLETED"
            run.summary = message("assistant.data.completed", count=len(rendered))
            run.state = {**run.state, "reviewed": False}
            db.add(
                Message(
                    conversation_id=run.conversation_id,
                    role="assistant",
                    content=run.summary,
                    details={"run_id": run.id, "kind": "results"},
                )
            )
            output = {"artifacts": len(rendered)}
        else:
            plan = DataPlan.model_validate(run.plan)
            operation = next(s for s in plan.steps if s.id == phase)
            inputs = [datasets.load_snapshot(state["datasets"][ref]) for ref in operation.inputs]
            context = {
                "step_id": phase,
                "request": run.request,
                "rules": state.get("rules", []),
                "decisions": state.get("decisions", {}),
                "use_model": settings.processing_mode == "LOCAL_LLM",
                "model_call": model_caller(db, run.id),
            }
            cache_ref = step.output.get("snapshot") or state.get("classification_cache", {}).get(phase)
            if cache_ref and operation.tool == "classify_values":
                cached = datasets.load_snapshot(cache_ref)
                context["assignments"] = {
                    a["key"]: a for a in cached.get("assignments", []) if a.get("method") == "model"
                }
            data = orchestration.execute_tool(operation, inputs, context)
            output = {"snapshot": datasets.save_snapshot(data), "rows": len(data["rows"]), "columns": data["columns"]}
            db.refresh(run)
            if run.status == "CANCELLED":
                return True
            refs = dict(run.state.get("datasets", {}))
            refs[phase] = output["snapshot"]
            run.state = {**run.state, "datasets": refs}
            if data.get("pending_model_keys"):
                complete_step(db, run, step, output, time.monotonic() - started)
                step.status = "PENDING"
                db.commit()
                return False
            if data.get("issues"):
                key = (
                    "assistant.data.needs_classification"
                    if all(issue.get("kind") == "classification" for issue in data["issues"])
                    else "assistant.data.needs_validation"
                )
                pause(db, run, message(key, count=len(data["issues"])), data["issues"])
        complete_step(db, run, step, output, time.monotonic() - started)
    except InputError as error:
        db.rollback()
        run = crud.run(db, job.payload["run_id"])
        step = queries.step(db, run.id, phase)
        if run.status != "CANCELLED":
            step.status, step.error = "NEEDS_INPUT", str(error.detail)
            pause(db, run, str(error.detail), error.issues or None)
            run.state = {
                **run.state,
                "elapsed_seconds": run.state.get("elapsed_seconds", 0) + time.monotonic() - started,
            }
        db.commit()
        return True
    except Exception:
        db.rollback()
        run = crud.run(db, job.payload["run_id"])
        step = queries.step(db, run.id, phase)
        step.status = "FAILED"
        run.state = {**run.state, "elapsed_seconds": run.state.get("elapsed_seconds", 0) + time.monotonic() - started}
        db.commit()
        raise
    return run.status in {"COMPLETED", "NEEDS_INPUT", "CANCELLED"}


def validate_results(run, plan):
    results = {ref: datasets.load_snapshot(value) for ref, value in run.state["datasets"].items()}
    for ref in {plan.result, plan.summary} - {None}:
        if results[ref].get("issues"):
            raise InputError(message("assistant.data.unresolved"))
    template = run.source_snapshot.get("template")
    if template:
        fields = set(template["fields"])
        fields.update(
            field for rewrite in plan.rewrites for field in task_documents.documents.slots([{"text": rewrite.text}])
        )
        missing = fields - {"total_rows", "source_rows", "summary_table"} - set(plan.bindings) - set(plan.tables)
        if missing:
            raise InputError(message("assistant.data.missing_binding", field=", ".join(sorted(missing))))
        for binding in plan.bindings.values():
            task_documents.metric_value(binding, results)
    checks = [check for ref in {plan.result, plan.summary} - {None} for check in results[ref].get("checks", [])]
    return {"passed": True, "detail_rows": len(results[plan.result]["rows"]), "checks": checks}


def render_outputs(run, plan, sources):
    snapshots = {key: datasets.load_snapshot(ref) for key, ref in run.state["datasets"].items()}
    detail = snapshots[plan.result]
    named = [("Details", detail)]
    if plan.summary and plan.summary != plan.result:
        named.insert(0, ("Summary", snapshots[plan.summary]))
    provenance = {
        "kind": "data_task",
        "run_id": run.id,
        "task_revision": run.revision,
        "sources": run.source_snapshot["sources"],
        "result": plan.result,
        "summary": plan.summary,
        "validation": run.state.get("validation", {}),
        "manually_edited": False,
    }
    outputs = [(datasets.workbook_bytes(named), "Analysis.xlsx", [], provenance)]
    template = next((item for item in sources if item["role"] == "template"), None)
    if template:
        content, name, paragraphs, bindings = task_documents.render_report(
            template,
            read_bytes(template["storage_key"], template["sha256"]),
            plan,
            snapshots,
            run.source_snapshot["source_rows"],
        )
        outputs.append((content, name, paragraphs, {**provenance, "report_bindings": bindings}))
    result = []
    for content, name, paragraphs, source in outputs:
        key, checksum = store_bytes(content)
        result.append(
            {
                "name": name,
                "label": message("assistant.data.report_label")
                if name.startswith("Report")
                else message("assistant.data.workbook_label"),
                "storage_key": key,
                "paragraphs": paragraphs,
                "provenance": {**source, "generated_sha256": checksum},
                "email": {},
            }
        )
    return result


def dataset_view(db, conversation_id, run_id, user, reference=None, offset=0, limit=50):
    run = require_run(db, conversation_id, run_id, user, lock=False)
    refs = run.state.get("datasets", {})
    reference = reference or run.plan.get("summary") or run.plan.get("result")
    if reference not in refs:
        raise AppError(404, message("assistant.data.dataset_not_found"))
    data = datasets.load_snapshot(refs[reference])
    return {
        "reference": reference,
        "columns": data["columns"],
        "total": len(data["rows"]),
        "rows": data["rows"][offset : offset + limit],
        "offset": offset,
    }


def cancel(db, conversation_id, run_id, user):
    run = require_run(db, conversation_id, run_id, user)
    if run.status in {"COMPLETED", "CANCELLED"}:
        raise AppError(409, message("assistant.data.not_active"))
    run.status, run.summary = "CANCELLED", message("assistant.data.cancelled")
    db.add(
        AuditLog(conversation_id=conversation_id, actor=user.username, action="CANCEL_TASK", details={"run_id": run_id})
    )
    db.commit()
    return {"ok": True}


def revise(db, conversation_id, run_id, user, body):
    run = require_run(db, conversation_id, run_id, user)
    previous = crud.find_message(db, conversation_id, body.request_key)
    if previous:
        previous_run = crud.run_for_message(db, previous.id)
        return {
            "conversation_id": conversation_id,
            "message_id": previous.id,
            "run_id": previous_run.id if previous_run else None,
        }
    if run.revision != body.revision or run.state.get("superseded_by"):
        raise AppError(409, message("assistant.data.stale_revision"))
    if run.status in {"QUEUED", "RUNNING"}:
        raise AppError(409, message("assistant.data.busy"))
    plan = DataPlan.model_validate(run.plan) if run.plan else None
    decisions = copy.deepcopy(run.state.get("decisions", {}))
    active_rules = [rule_view(r) for r in queries.rules(db, user.id)]
    for decision in body.decisions:
        operation = next(
            (s for s in (plan.steps if plan else []) if s.id == decision.step_id and s.tool == "classify_values"), None
        )
        if not operation:
            raise AppError(422, message("assistant.data.invalid_decision"))
        receipt = queries.step(db, run.id, decision.step_id)
        if not receipt or "snapshot" not in receipt.output:
            raise AppError(422, message("assistant.data.invalid_decision"))
        assignments = datasets.load_snapshot(receipt.output["snapshot"]).get("assignments", [])
        assignment = next((item for item in assignments if item["key"] == decision.key), None)
        if not assignment or decision.category not in operation.arguments["categories"]:
            raise AppError(422, message("assistant.data.invalid_decision"))
        decisions.setdefault(decision.step_id, {})[decision.key] = decision.category
        if decision.save_rule:
            existing = [
                r
                for r in queries.rules(db, user.id)
                if r.source_column == operation.arguments["column"]
                and r.source_value == decision.key
                and set(r.categories) == set(operation.arguments["categories"])
            ]
            version = max((r.version for r in existing), default=0) + 1
            for old in existing:
                old.status = "RETIRED"
                old.version += 1
            saved = BusinessRule(
                user_id=user.id,
                source_column=operation.arguments["column"],
                source_value=decision.key,
                category=decision.category,
                categories=operation.arguments["categories"],
                version=version,
                run_id=run.id,
            )
            db.add(saved)
            db.flush()
            active_rules = [rule_view(r) for r in queries.rules(db, user.id)]
    if not body.decisions and not body.text.strip():
        raise AppError(422, message("assistant.data.empty_revision"))
    msg = Message(
        conversation_id=conversation_id,
        request_key=body.request_key,
        role="user",
        content=body.text.strip() or message("assistant.data.review_decisions", count=len(body.decisions)),
        details={"parent_run_id": run.id},
    )
    db.add(msg)
    db.flush()
    request = run.request + ("\nUser clarification: " + body.text if body.text else "")
    if len(request) > 14000:
        raise AppError(422, message("assistant.data.request_limit"))
    new_state = {"decisions": decisions, "rules": active_rules, "model_calls": 0}
    if not body.text and plan:
        # Report mappings depend on computed groups and must be rebound after any correction.
        plan.bindings, plan.tables, plan.rewrites = {}, {}, []
        new_state["supplied_plan"] = plan.model_dump()
        new_state["classification_cache"] = {
            step.step_id: step.output["snapshot"]
            for step in queries.steps(db, run.id)
            if step.tool == "classify_values" and step.output.get("snapshot")
        }
    new_run = GenerationRun(
        conversation_id=conversation_id,
        message_id=msg.id,
        method=run.method,
        request=request,
        attachment_ids=list(run.attachment_ids),
        kind="DATA_TASK",
        revision=run.revision + 1,
        parent_run_id=run.id,
        state=new_state,
    )
    db.add(new_run)
    db.flush()
    run.state = {**run.state, "superseded_by": new_run.id, "reviewed": False}
    for artifact in crud.list_artifacts(db, run.id):
        artifact.reviewed = False
    job = enqueue(db, "ASSISTANT_GENERATE", "assistant:" + new_run.id, {"run_id": new_run.id})
    job.max_attempts = 2
    conversation = crud.conversation(db, conversation_id)
    conversation.context = {
        **conversation.context,
        "attachment_ids": list(run.attachment_ids),
        "request": request,
        "task_mode": "data",
    }
    conversation.updated_at = utcnow()
    db.add(
        AuditLog(
            conversation_id=conversation_id,
            actor=user.username,
            action="REVISE_TASK",
            details={"run_id": run.id, "new_run_id": new_run.id, "decisions": len(body.decisions)},
        )
    )
    db.commit()
    return {"conversation_id": conversation_id, "message_id": msg.id, "run_id": new_run.id}


def review(db, conversation_id, run_id, user, body):
    run = require_run(db, conversation_id, run_id, user)
    if run.revision != body.revision or run.state.get("superseded_by") or run.status != "COMPLETED":
        raise AppError(409, message("assistant.data.stale_revision"))
    if run.state.get("issues") or not run.state.get("validation", {}).get("passed"):
        raise AppError(409, message("assistant.data.unresolved"))
    run.state = {**run.state, "reviewed": body.reviewed, "reviewed_by": user.username}
    for artifact in crud.list_artifacts(db, run.id):
        artifact.reviewed = body.reviewed
    db.add(
        AuditLog(
            conversation_id=conversation_id,
            actor=user.username,
            action="REVIEW_TASK",
            details={"run_id": run.id, "revision": run.revision, "reviewed": body.reviewed},
        )
    )
    db.commit()
    return {"ok": True}


def retire_rule(db, rule_id, user, version):
    rule = queries.rule(db, rule_id, user.id)
    if not rule:
        raise AppError(404, message("assistant.data.rule_not_found"))
    if rule.version != version:
        raise AppError(409, message("assistant.data.stale_revision"))
    rule.status, rule.version = "RETIRED", rule.version + 1
    db.add(
        AuditLog(
            conversation_id=crud.run(db, rule.run_id).conversation_id,
            actor=user.username,
            action="RETIRE_RULE",
            details={"rule_id": rule.id, "version": rule.version},
        )
    )
    db.commit()
    return {"ok": True}


def classifications(db, conversation_id, run_id, user, offset=0, limit=50):
    require_run(db, conversation_id, run_id, user, lock=False)
    result = []
    for receipt in queries.steps(db, run_id):
        if receipt.tool != "classify_values" or not receipt.output.get("snapshot"):
            continue
        data = datasets.load_snapshot(receipt.output["snapshot"])
        for assignment in data.get("assignments", []):
            result.append({"step_id": receipt.step_id, **assignment})
    return {"total": len(result), "rows": result[offset : offset + limit], "offset": offset}
