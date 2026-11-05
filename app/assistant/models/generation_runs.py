from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class AssistantGenerationRun(Base):
    __tablename__ = "assistant_generation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("assistant_conversations.id"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("assistant_messages.id"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    method: Mapped[str] = mapped_column(String(30))
    request: Mapped[str] = mapped_column(Text)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    report: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    attachment_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    kind: Mapped[str] = mapped_column(String(20), default="DOCUMENT", server_default="DOCUMENT")
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    parent_run_id: Mapped[str | None] = mapped_column(ForeignKey("assistant_generation_runs.id"), nullable=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
