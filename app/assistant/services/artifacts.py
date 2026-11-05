import csv
import hashlib
import io
import json
import re
import zipfile
from email.message import EmailMessage
from pathlib import Path

from app.assistant.crud import conversations as crud
from app.assistant.errors import AppError
from app.assistant.models import AuditLog
from app.assistant.services.conversations import artifact_view, require_conversation
from app.assistant.services.documents import edit_document, paragraphs
from app.assistant.services.storage import read_bytes, store_bytes
from app.core.i18n import message


def source_download(db, attachment_id, user):
    import mimetypes

    item = crud.attachment(db, attachment_id)
    if not item:
        raise AppError(404, "Không tìm thấy file nguồn.")
    require_conversation(db, item.conversation_id, user.id)
    return (
        read_bytes(item.storage_key, item.sha256),
        item.name,
        mimetypes.guess_type(item.name)[0] or "application/octet-stream",
    )


def require_artifact(db, artifact_id, user, *, lock=False):
    item = crud.artifact(db, artifact_id, lock=lock)
    if not item:
        raise AppError(404, "Không tìm thấy hồ sơ.")
    run = crud.run(db, item.run_id)
    require_conversation(db, run.conversation_id, user.id)
    return item, run


def edit(db, artifact_id, user, body):
    item, run = require_artifact(db, artifact_id, user, lock=True)
    if run.kind == "DATA_TASK":
        raise AppError(409, message("assistant.data.bound_artifact"))
    if item.revision != body.revision:
        raise AppError(409, "Hồ sơ đã được cập nhật ở cửa sổ khác. Hãy tải lại trước khi sửa.")
    edits = [p.model_dump() for p in body.paragraphs]
    if len({p["id"] for p in edits}) != len(edits):
        raise AppError(422, "Một đoạn tài liệu bị lặp trong yêu cầu sửa.")
    original = read_bytes(item.storage_key)
    content = edit_document(original, edits)
    key, digest = store_bytes(content)
    previous = item.revision
    item.storage_key = key
    item.paragraphs = paragraphs(content)
    item.revision += 1
    item.reviewed = False
    item.provenance = {**item.provenance, "manually_edited": True, "current_sha256": digest}
    db.add(
        AuditLog(
            conversation_id=run.conversation_id,
            actor=user.username,
            action="EDIT_ARTIFACT",
            details={
                "artifact_id": item.id,
                "previous_revision": previous,
                "revision": item.revision,
                "previous_sha256": hashlib.sha256(original).hexdigest(),
                "sha256": digest,
            },
        )
    )
    db.commit()
    return artifact_view(item)


def review(db, artifact_id, user, body):
    item, run = require_artifact(db, artifact_id, user, lock=True)
    if run.kind == "DATA_TASK":
        raise AppError(409, message("assistant.data.review_bundle"))
    if item.revision != body.revision:
        raise AppError(409, "Phiên bản đã đổi. Hãy kiểm tra bản mới trước khi xác nhận.")
    item.reviewed = body.reviewed
    db.add(
        AuditLog(
            conversation_id=run.conversation_id,
            actor=user.username,
            action="REVIEW_ARTIFACT",
            details={"artifact_id": item.id, "revision": item.revision, "reviewed": body.reviewed},
        )
    )
    db.commit()
    return artifact_view(item)


def email_bytes(email):
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email.get("to", "")):
        raise AppError(422, "Hồ sơ chưa có địa chỉ email hợp lệ; chỉ tải được nội dung tài liệu.")
    message = EmailMessage()
    message["X-Unsent"] = "1"
    message["To"] = email["to"]
    message["Subject"] = email.get("subject", "").replace("\r", " ").replace("\n", " ")
    message.set_content(email.get("body", ""), charset="utf-8")
    return message.as_bytes()


def download(db, artifact_id, user, kind="docx"):
    item, _ = require_artifact(db, artifact_id, user)
    if kind == "eml":
        return email_bytes(item.email), item.name.removesuffix(".docx") + ".eml", "message/rfc822"
    return (
        read_bytes(item.storage_key, item.provenance.get("current_sha256") or item.provenance.get("generated_sha256")),
        item.name,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if Path(item.name).suffix.lower() == ".xlsx"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def preview(db, artifact_id, user, sheet=None, offset=0, limit=50):
    item, _ = require_artifact(db, artifact_id, user)
    if not item.name.lower().endswith(".xlsx"):
        return {"kind": "document", "paragraphs": item.paragraphs}
    from openpyxl import load_workbook

    from app.assistant.services.documents import cell_value

    content = read_bytes(item.storage_key, item.provenance.get("generated_sha256"))
    book = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
    try:
        sheet_name = sheet or book.sheetnames[0]
        if sheet_name not in book.sheetnames:
            raise AppError(404, message("assistant.data.dataset_not_found"))
        selected = book[sheet_name]
        rows = [
            [cell_value(cell.value) for cell in row]
            for row in selected.iter_rows(
                min_row=offset + 1, max_row=min(offset + limit, selected.max_row), max_col=min(selected.max_column, 80)
            )
        ]
        return {
            "kind": "workbook",
            "sheets": book.sheetnames,
            "sheet": sheet_name,
            "rows": rows,
            "total": selected.max_row,
            "offset": offset,
        }
    finally:
        book.close()


def report_bytes(run):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Bản ghi", "Trạng thái", "Lý do", "Nguồn"])
    for row in run.report:
        values = [
            row.get("record", ""),
            row.get("status", ""),
            row.get("reason", ""),
            json.dumps(row.get("source", {}), ensure_ascii=False),
        ]
        writer.writerow(["'" + str(v) if str(v).startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values])
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def run_download(db, run_id, user, kind="zip"):
    run = crud.run(db, run_id)
    if not run:
        raise AppError(404, "Không tìm thấy bộ hồ sơ.")
    require_conversation(db, run.conversation_id, user.id)
    if kind == "csv":
        if run.kind == "DATA_TASK":
            from app.assistant.services import datasets

            reference = run.plan.get("summary") or run.plan.get("result")
            refs = run.state.get("datasets", {})
            if reference not in refs:
                raise AppError(409, message("assistant.data.dataset_not_found"))
            data = datasets.load_snapshot(refs[reference])
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(data["columns"])
            for row in data["rows"]:
                writer.writerow(
                    [
                        "'" + str(value) if str(value).startswith(("=", "+", "-", "@", "\t", "\r")) else value
                        for value in [row["values"].get(c, "") for c in data["columns"]]
                    ]
                )
            return ("\ufeff" + stream.getvalue()).encode(), "Summary.csv", "text/csv; charset=utf-8"
        return report_bytes(run), "Bao_cao_xu_ly.csv", "text/csv; charset=utf-8"
    if run.status != "COMPLETED":
        raise AppError(409, "Bộ hồ sơ chưa được tạo xong.")
    items = crud.list_artifacts(db, run.id)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        metadata = []
        for item in items:
            archive.writestr("Ho_so/" + item.name, read_bytes(item.storage_key))
            if item.email and re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", item.email.get("to", "")):
                archive.writestr("Email/" + item.name.removesuffix(".docx") + ".eml", email_bytes(item.email))
            metadata.append(
                {"file": item.name, "revision": item.revision, "reviewed": item.reviewed, "provenance": item.provenance}
            )
        archive.writestr("Bao_cao_xu_ly.csv", report_bytes(run))
        archive.writestr(
            "Nguon_va_phien_ban.json",
            json.dumps(
                {"run_id": run.id, "method": run.method, "plan": run.plan, "artifacts": metadata},
                ensure_ascii=False,
                indent=2,
            ),
        )
        if run.kind == "DATA_TASK":
            from app.assistant.services import datasets

            refs = {ref for ref in (run.plan.get("result"), run.plan.get("summary")) if ref}
            archive.writestr(
                "Lineage.json",
                json.dumps(
                    {ref: datasets.load_snapshot(run.state["datasets"][ref]) for ref in refs}, ensure_ascii=False
                ),
            )
        archive.writestr(
            "DOC_TOI.txt",
            "Hồ sơ là bản nháp. Kiểm tra trước khi sử dụng. Không có email nào được gửi và không phát hành văn bản.\nPDF scan/OCR và tự động phát hành nằm ngoài MVP.\n",
        )
    db.add(
        AuditLog(
            conversation_id=run.conversation_id,
            actor=user.username,
            action="EXPORT",
            details={"run_id": run.id, "count": len(items)},
        )
    )
    db.commit()
    return stream.getvalue(), "DraftV_ho_so_nhap.zip", "application/zip"
