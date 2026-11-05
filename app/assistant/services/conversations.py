from pathlib import Path

from app.assistant.config import settings
from app.assistant.crud import conversations as crud
from app.assistant.crud import tasks as task_queries
from app.assistant.errors import AppError
from app.assistant.models import Attachment, AuditLog, Conversation, GenerationRun, Message
from app.assistant.services import task_planner, tasks
from app.assistant.services.storage import store_bytes
from app.core.i18n import message as localized
from app.core.time import utcnow
from app.crud.jobs import enqueue


def require_conversation(db, conversation_id, user_id, *, lock=False):
    conversation = crud.owned(db, conversation_id, user_id, lock=lock)
    if not conversation:
        raise AppError(404, "Không tìm thấy cuộc hội thoại.")
    return conversation


def conversation_view(item):
    return {"id": item.id, "title": item.title, "updated_at": item.updated_at.isoformat()}


def attachment_view(item):
    return {"id": item.id, "name": item.name, "role": item.role, "size": item.size, "sha256": item.sha256}


def audit(db, conversation_id, user):
    require_conversation(db, conversation_id, user.id)
    return [
        {"actor": item.actor, "action": item.action, "details": item.details, "created_at": item.created_at.isoformat()}
        for item in crud.list_audit(db, conversation_id)
    ]


def artifact_view(item):
    return {
        key: getattr(item, key)
        for key in ["id", "run_id", "name", "label", "paragraphs", "provenance", "email", "revision", "reviewed"]
    }


def list_conversations(db, user):
    return [conversation_view(c) for c in crud.list_conversations(db, user.id)]


def create_conversation(db, user):
    conversation = Conversation(user_id=user.id)
    db.add(conversation)
    db.commit()
    return conversation_view(conversation)


def detail(db, conversation_id, user):
    conversation = require_conversation(db, conversation_id, user.id)
    runs = []
    for run in crud.list_runs(db, conversation_id):
        job = crud.job_for_run(db, run.id)
        runs.append(
            {
                "id": run.id,
                "status": run.status,
                "method": run.method,
                "summary": run.summary,
                "plan": run.plan,
                "report": run.report,
                "artifacts": [artifact_view(a) for a in crud.list_artifacts(db, run.id)],
                "job": {"status": job.status, "attempts": job.attempts, "error": job.error} if job else None,
                "kind": run.kind,
                "revision": run.revision,
                "parent_run_id": run.parent_run_id,
                "steps": [tasks.step_view(step) for step in task_queries.steps(db, run.id)]
                if run.kind == "DATA_TASK"
                else [],
                "task": {
                    "phase": run.state.get("phase"),
                    "issues": run.state.get("issues", [])[:200],
                    "issue_count": len(run.state.get("issues", [])),
                    "reviewed": run.state.get("reviewed", False),
                    "superseded_by": run.state.get("superseded_by"),
                    "validation": run.state.get("validation"),
                    "catalog": [
                        {k: v for k, v in item.items() if k not in {"samples", "distinct"}}
                        for item in run.state.get("catalog", [])
                    ],
                    "datasets": list(run.state.get("datasets", {})),
                }
                if run.kind == "DATA_TASK"
                else {},
            }
        )
    return {
        **conversation_view(conversation),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "details": m.details,
                "created_at": m.created_at.isoformat(),
            }
            for m in crud.list_messages(db, conversation_id)
        ],
        "attachments": [attachment_view(a) for a in crud.list_attachments(db, conversation_id)],
        "runs": runs,
    }


def upload(db, conversation_id, user, name, role, content):
    conversation = require_conversation(db, conversation_id, user.id, lock=True)
    if role not in {"template", "data"}:
        raise AppError(422, "Vai trò file phải là mẫu hoặc dữ liệu.")
    name = Path((name or "file").replace("\\", "/")).name[:220]
    supported = {".docx", ".txt", ".xlsx"} if role == "template" else {".xlsx", ".csv", ".txt", ".docx", ".pdf"}
    if Path(name).suffix.lower() not in supported:
        raise AppError(422, localized("assistant.data.supported_formats"))
    if not content or len(content) > settings.max_upload_bytes:
        raise AppError(413, "File trống hoặc vượt 15 MB.")
    storage_key, digest = store_bytes(content)
    item = Attachment(
        conversation_id=conversation.id, name=name, role=role, storage_key=storage_key, sha256=digest, size=len(content)
    )
    db.add(item)
    conversation.updated_at = utcnow()
    db.add(
        AuditLog(
            conversation_id=conversation_id,
            actor=user.username,
            action="UPLOAD",
            details={"name": name, "role": role, "sha256": digest},
        )
    )
    db.commit()
    return attachment_view(item)


def add_message(db, conversation_id, user, body):
    conversation = require_conversation(db, conversation_id, user.id, lock=True)
    previous = crud.find_message(db, conversation_id, body.request_key)
    if previous:
        run = crud.run_for_message(db, previous.id)
        return {"conversation_id": conversation_id, "message_id": previous.id, "run_id": run.id if run else None}
    runs = crud.list_runs(db, conversation_id)
    if any(r.status in {"QUEUED", "RUNNING"} for r in runs):
        raise AppError(409, "Trợ lý đang xử lý yêu cầu trước. Bạn đợi hoàn tất rồi gửi tiếp nhé.")
    context = conversation.context or {}
    mode = body.task_mode if body.task_mode != "auto" else context.get("task_mode", "auto")
    ids = body.attachment_ids or context.get("attachment_ids", [])
    items = [crud.attachment(db, item_id) for item_id in ids]
    if any(not item or item.conversation_id != conversation_id for item in items):
        raise AppError(404, "Không tìm thấy file trong cuộc hội thoại này.")
    if len(set(ids)) != len(ids):
        raise AppError(422, localized("assistant.data.duplicate_source"))
    if mode == "auto":
        mode = (
            "data"
            if task_planner.is_data_request(body.text)
            or len(items) != 2
            or not any(item.role == "template" for item in items)
            or any(item.role == "template" and item.name.lower().endswith(".xlsx") for item in items)
            else "documents"
        )
    if (
        mode == "data"
        and not body.attachment_ids
        and runs
        and runs[-1].kind == "DATA_TASK"
        and runs[-1].status not in {"QUEUED", "RUNNING", "CANCELLED"}
    ):
        from app.assistant.schema.tasks import ResumeTask

        return tasks.revise(
            db,
            conversation_id,
            runs[-1].id,
            user,
            ResumeTask(revision=runs[-1].revision, text=body.text, request_key=body.request_key),
        )
    message = Message(
        conversation_id=conversation_id,
        request_key=body.request_key,
        role="user",
        content=body.text,
        details={"attachment_ids": ids if body.attachment_ids else []},
    )
    db.add(message)
    db.flush()
    valid_inputs = (
        (any(item.role == "data" for item in items) and sum(item.role == "template" for item in items) <= 1)
        if mode == "data"
        else (len(items) == 2 and {item.role for item in items} == {"template", "data"})
    )
    if not valid_inputs:
        db.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content=localized("assistant.data.attach_sources")
                if mode == "data"
                else "Bạn đính kèm một file mẫu (DOCX/TXT) và một file dữ liệu (Excel, CSV, TXT, Word hoặc PDF có text) nhé. Tôi sẽ dùng hai file đó để hoàn thiện hồ sơ theo yêu cầu.",
            )
        )
        db.commit()
        return {"conversation_id": conversation_id, "message_id": message.id, "run_id": None}
    request = body.text if body.attachment_ids else context.get("request", "") + "\nNgười dùng bổ sung: " + body.text
    if len(request) > 14000:
        raise AppError(422, "Hội thoại xử lý đã dài. Hãy bắt đầu yêu cầu mới với hai file và mô tả đầy đủ.")
    run = GenerationRun(
        conversation_id=conversation_id,
        message_id=message.id,
        method=settings.processing_mode,
        request=request,
        attachment_ids=ids,
        kind="DATA_TASK" if mode == "data" else "DOCUMENT",
    )
    db.add(run)
    db.flush()
    job = enqueue(db, "ASSISTANT_GENERATE", "assistant:" + run.id, {"run_id": run.id})
    job.max_attempts = 2
    conversation.context = {"attachment_ids": ids, "request": request, "task_mode": mode}
    conversation.updated_at = utcnow()
    if len(runs) == 0:
        conversation.title = body.text.strip()[:90]
    db.add(
        AuditLog(
            conversation_id=conversation_id,
            actor=user.username,
            action="REQUEST",
            details={"run_id": run.id, "attachment_ids": ids, "method": settings.processing_mode},
        )
    )
    db.commit()
    return {"conversation_id": conversation_id, "message_id": message.id, "run_id": run.id}


def retry(db, conversation_id, run_id, user):
    require_conversation(db, conversation_id, user.id, lock=True)
    run = crud.run(db, run_id)
    if not run or run.conversation_id != conversation_id:
        raise AppError(404, "Không tìm thấy lần xử lý.")
    job = crud.job_for_run(db, run_id)
    if not job or job.status != "FAILED":
        raise AppError(409, "Chỉ thử lại công việc đã thất bại.")
    if any(r.status in {"QUEUED", "RUNNING"} for r in crud.list_runs(db, conversation_id)):
        raise AppError(409, "Đang có một yêu cầu khác được xử lý.")
    job.status, job.attempts, job.error, job.locked_at = "PENDING", 0, None, None
    job.available_at = utcnow()
    run.status = "QUEUED"
    run.summary = ""
    db.add(AuditLog(conversation_id=conversation_id, actor=user.username, action="RETRY", details={"run_id": run.id}))
    db.commit()
    return {"ok": True}
