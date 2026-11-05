from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import DBSession, HRUser
from app.assistant.config import settings
from app.assistant.demo.generate import PROMPT, files
from app.assistant.errors import AppError
from app.assistant.schema.chat import AttachmentView, ConversationDetail, ConversationView, MessageAck, MessageRequest
from app.assistant.services import conversations as service
from app.core.i18n import message as localized

router = APIRouter(prefix="/conversations")


@router.get("", response_model=list[ConversationView])
def list_conversations(db: DBSession, user: HRUser):
    return service.list_conversations(db, user)


@router.post("", response_model=ConversationView)
def create(db: DBSession, user: HRUser):
    return service.create_conversation(db, user)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def detail(conversation_id: str, db: DBSession, user: HRUser):
    return service.detail(db, conversation_id, user)


@router.get("/{conversation_id}/audit")
def audit(conversation_id: str, db: DBSession, user: HRUser):
    return service.audit(db, conversation_id, user)


@router.post("/{conversation_id}/attachments", response_model=AttachmentView)
async def upload(
    conversation_id: str, db: DBSession, user: HRUser, role: str = Form(...), file: UploadFile = File(...)
):
    content = bytearray()
    while chunk := await file.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > settings.max_upload_bytes:
            raise AppError(413, "File vượt giới hạn 15 MB.")
    return service.upload(db, conversation_id, user, file.filename, role, bytes(content))


@router.post("/{conversation_id}/messages", response_model=MessageAck, status_code=202)
def message(conversation_id: str, body: MessageRequest, db: DBSession, user: HRUser):
    return service.add_message(db, conversation_id, user, body)


@router.post("/{conversation_id}/runs/{run_id}/retry")
def retry(conversation_id: str, run_id: str, db: DBSession, user: HRUser):
    return service.retry(db, conversation_id, run_id, user)


@router.post("/{conversation_id}/demo")
def demo(conversation_id: str, db: DBSession, user: HRUser, missing: bool = False, plain_template: bool = False):
    service.require_conversation(db, conversation_id, user.id)
    items = [
        service.upload(db, conversation_id, user, name, role, content)
        for name, role, content in files(missing, plain_template)
    ]
    return {"attachments": items, "prompt": PROMPT}


@router.post("/{conversation_id}/demo-data")
def demo_data(conversation_id: str, db: DBSession, user: HRUser):
    from app.assistant.demo.data_tasks import files as data_files

    service.require_conversation(db, conversation_id, user.id)
    items = [service.upload(db, conversation_id, user, name, role, content) for name, role, content in data_files()]
    return {"attachments": items, "prompt": localized("assistant.demo.data_prompt")}
