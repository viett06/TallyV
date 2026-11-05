from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.models import Artifact, Attachment, AuditLog, Conversation, GenerationRun, Message
from app.crud.jobs import get_by_key


def owned(db: Session, conversation_id: str, user_id: int, *, lock=False):
    query = select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    return db.scalar(query.with_for_update() if lock else query)


def list_conversations(db: Session, user_id: int):
    return list(
        db.scalars(select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc()))
    )


def list_messages(db: Session, conversation_id: str):
    return list(
        db.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at, Message.id)
        )
    )


def list_attachments(db: Session, conversation_id: str):
    return list(
        db.scalars(
            select(Attachment).where(Attachment.conversation_id == conversation_id).order_by(Attachment.created_at)
        )
    )


def list_runs(db: Session, conversation_id: str):
    return list(
        db.scalars(
            select(GenerationRun)
            .where(GenerationRun.conversation_id == conversation_id)
            .order_by(GenerationRun.created_at)
        )
    )


def list_artifacts(db: Session, run_id: str):
    return list(
        db.scalars(select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at, Artifact.id))
    )


def find_message(db: Session, conversation_id: str, key: str):
    return db.scalar(select(Message).where(Message.conversation_id == conversation_id, Message.request_key == key))


def run_for_message(db: Session, message_id: str):
    return db.scalar(select(GenerationRun).where(GenerationRun.message_id == message_id))


def job_for_run(db: Session, run_id: str):
    return get_by_key(db, "assistant:" + run_id)


def list_audit(db: Session, conversation_id: str):
    return list(db.scalars(select(AuditLog).where(AuditLog.conversation_id == conversation_id).order_by(AuditLog.id)))


def attachment(db: Session, attachment_id: str):
    return db.get(Attachment, attachment_id)


def artifact(db: Session, artifact_id: str, *, lock=False):
    query = select(Artifact).where(Artifact.id == artifact_id)
    return db.scalar(query.with_for_update() if lock else query)


def run(db: Session, run_id: str):
    return db.get(GenerationRun, run_id)


def conversation(db: Session, conversation_id: str):
    return db.get(Conversation, conversation_id)
