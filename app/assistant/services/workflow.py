import copy
import hashlib
import re
from datetime import date

from app.assistant.crud import conversations as crud
from app.assistant.errors import InputError
from app.assistant.models import Artifact, AuditLog, Message
from app.assistant.services import documents, planner
from app.assistant.services.storage import read_bytes, store_bytes
from app.core.time import utcnow


def ask(db, run, text, details=None):
    run.status = "NEEDS_INPUT"
    run.summary = text
    db.add(
        Message(
            conversation_id=run.conversation_id,
            role="assistant",
            content=text,
            details={"run_id": run.id, "kind": "clarification", **(details or {})},
        )
    )


def compare_filter(values, condition):
    value = str(values.get(condition.column, "")).strip()
    if condition.operator == "date_month":
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise InputError(f"Cột {condition.column} cần ngày ISO YYYY-MM-DD đã xác nhận.") from None
        return parsed.strftime("%Y-%m") == condition.value
    a, b = planner.plain(value), planner.plain(condition.value)
    return {"eq": a == b, "ne": a != b, "contains": b in a}[condition.operator]


def fill_text(text, context):
    return documents.SLOT.sub(lambda m: str(context.get(m.group(1).strip(), m.group(0))), text)


def process(db, run):
    if run.status == "COMPLETED":
        return
    items = [crud.attachment(db, item_id) for item_id in run.attachment_ids]
    if any(item is None or item.conversation_id != run.conversation_id for item in items):
        raise InputError("Nguồn file không còn hợp lệ.")
    template = next(item for item in items if item.role == "template")
    source = next(item for item in items if item.role == "data")
    template_bytes, paragraphs = documents.load_template(
        template.name, read_bytes(template.storage_key, template.sha256)
    )
    parsed = documents.parse_data(source.name, read_bytes(source.storage_key, source.sha256))
    hints = documents.slots(paragraphs) or [
        label for item in paragraphs for label in re.findall(r"\[([^\[\]]+)\]", item["text"])
    ]
    records = parsed["records"] or planner.extract_records(parsed["text"], source.name, hints, run.request)
    if not records:
        raise InputError("Dữ liệu không có bản ghi để tạo hồ sơ.")
    original = copy.deepcopy(records)
    run.status = "RUNNING"
    plan = planner.create_plan(run.request, paragraphs, records)
    run.plan = plan.model_dump()
    run.source_snapshot = {
        "template": {"id": template.id, "name": template.name, "sha256": template.sha256},
        "data": {"id": source.id, "name": source.name, "sha256": source.sha256},
        "record_count": len(records),
    }
    if plan.question:
        ask(db, run, plan.question)
        return
    for correction in plan.corrections:
        records[correction.row - 1]["values"][correction.column] = correction.value
    normalized = [
        {"text": next((r.text for r in plan.rewrites if r.paragraph_id == p["id"]), p["text"])} for p in paragraphs
    ]
    required = documents.slots(normalized)
    report = []
    ready = []
    missing = []
    fingerprints = set()
    for index, record in enumerate(records):
        values = record["values"]
        entry = {"record": index + 1, "source": record["source"], "status": "", "reason": ""}
        try:
            chosen = all(compare_filter(values, f) for f in plan.filters)
        except InputError as error:
            chosen = True
            entry["reason"] = error.detail
        if not chosen:
            report.append({**entry, "status": "NOT_SELECTED", "reason": "Không khớp điều kiện trong yêu cầu."})
            continue
        context = {key: values.get(column, "") for key, column in plan.mapping.items()}
        context.update(plan.constants)
        fields = [field for field in required if not str(context.get(field, "")).strip()]
        fingerprint = hashlib.sha256(repr(sorted(values.items())).encode()).hexdigest()
        if fingerprint in fingerprints:
            entry["reason"] = "Bản ghi trùng hoàn toàn với một dòng trước đó."
        fingerprints.add(fingerprint)
        if fields or entry["reason"]:
            detail = {
                "record": index + 1,
                "source": record["source"],
                "fields": [plan.mapping.get(f, f) for f in fields],
                "label": next(
                    (v for k, v in values.items() if planner.compact(k) in {"hoten", "hovaten", "fullname", "name"}),
                    f"Bản ghi {index + 1}",
                ),
                "reason": entry["reason"],
            }
            if plan.skip_incomplete:
                report.append(
                    {**entry, "status": "SKIPPED", "reason": entry["reason"] or "Thiếu " + ", ".join(detail["fields"])}
                )
            else:
                missing.append(detail)
                report.append(
                    {
                        **entry,
                        "status": "NEEDS_INPUT",
                        "reason": entry["reason"] or "Thiếu " + ", ".join(detail["fields"]),
                    }
                )
            continue
        ready.append((index, record, context))
        report.append({**entry, "status": "READY"})
    run.report = report
    if missing:
        ask(
            db,
            run,
            f"Có {len(missing)} hồ sơ thiếu hoặc có dữ liệu cần xác nhận. Bạn có thể bổ sung thông tin hoặc yêu cầu bỏ qua các hồ sơ đó. Tôi chưa tự điền giá trị còn thiếu.",
            {"missing": missing},
        )
        return
    if not ready:
        ask(
            db,
            run,
            "Không có bản ghi đủ điều kiện theo yêu cầu hiện tại. Bạn kiểm tra lại điều kiện hoặc đính kèm dữ liệu khác nhé.",
        )
        return
    for index, record, context in ready:
        content = documents.render_template(template_bytes, context, [r.model_dump() for r in plan.rewrites])
        key, digest = store_bytes(content)
        values = record["values"]
        name_column = planner.alias_match("ho_ten", list(values))
        label = values.get(name_column, "") if name_column else f"Hồ sơ {index + 1}"
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", planner.plain(label))[:60]
        email_column = planner.alias_match("email", list(values))
        email = {}
        if plan.email_requested:
            email = {
                "to": values.get(email_column, "") if email_column else "",
                "subject": fill_text(plan.email_subject, context),
                "body": fill_text(plan.email_body, context),
            }
        provenance = {
            **run.source_snapshot,
            "record": index + 1,
            "source": record["source"],
            "original_values": original[index]["values"],
            "confirmed_values": values,
            "mapping": plan.mapping,
            "constants": plan.constants,
            "generated_sha256": digest,
            "method": run.method,
            "manually_edited": False,
            "format_note": "Giữ gói DOCX gốc; đoạn được AI chuẩn hóa có thể thay đổi định dạng chữ trong phần được điền."
            if plan.rewrites
            else "Điền vào placeholder, giữ thành phần DOCX gốc.",
        }
        db.add(
            Artifact(
                run_id=run.id,
                name=f"Ho_so_{index + 1:03}_{safe}.docx",
                label=label,
                storage_key=key,
                paragraphs=documents.paragraphs(content),
                provenance=provenance,
                email=email,
            )
        )
    for entry in report:
        if entry["status"] == "READY":
            entry["status"] = "CREATED"
    run.report = report
    run.status = "COMPLETED"
    omitted = len(report) - len(ready)
    run.summary = (
        f"Đã chuẩn bị {len(ready)} hồ sơ nháp theo mẫu. "
        + (f"{omitted} bản ghi không được tạo; xem báo cáo để biết lý do. " if omitted else "")
        + "Bạn có thể mở hồ sơ để kiểm tra, chỉnh sửa và tải xuống."
    )
    prior_runs = [
        item for item in crud.list_runs(db, run.conversation_id) if item.id != run.id and item.status == "COMPLETED"
    ]
    if any(
        artifact.provenance.get("manually_edited")
        for prior in prior_runs
        for artifact in crud.list_artifacts(db, prior.id)
    ):
        run.summary += (
            " Phiên mới được tạo lại từ file nguồn; chỉnh sửa trực tiếp ở phiên cũ vẫn được giữ trong phiên đó."
        )
    db.add(
        Message(
            conversation_id=run.conversation_id,
            role="assistant",
            content=run.summary,
            details={"run_id": run.id, "kind": "results"},
        )
    )
    db.add(
        AuditLog(
            conversation_id=run.conversation_id,
            actor="worker",
            action="GENERATE",
            details={"run_id": run.id, "count": len(ready), "method": run.method},
        )
    )
    conversation = crud.conversation(db, run.conversation_id)
    conversation.updated_at = utcnow()
