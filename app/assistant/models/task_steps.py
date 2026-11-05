"""Durable tool receipts and owner-scoped, explicitly confirmed business memory."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class AssistantTaskStep(Base):
    __tablename__ = "assistant_task_steps"
    __table_args__ = (UniqueConstraint("run_id", "step_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("assistant_generation_runs.id"), index=True)
    step_id: Mapped[str] = mapped_column(String(80))
    tool: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(default=0)
    elapsed_ms: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssistantBusinessRule(Base):
    __tablename__ = "assistant_business_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_column: Mapped[str] = mapped_column(String(160))
    source_value: Mapped[str] = mapped_column(String(1000))
    category: Mapped[str] = mapped_column(String(160))
    categories: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    version: Mapped[int] = mapped_column(default=1)
    run_id: Mapped[str] = mapped_column(ForeignKey("assistant_generation_runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
