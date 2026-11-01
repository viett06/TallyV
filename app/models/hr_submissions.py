from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class HrSubmission(Base):
    __tablename__ = "hr_submissions"
    __table_args__ = (Index("ix_hr_submissions_case_created", "case_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[int] = mapped_column(ForeignKey("attendance_cases.id"))
    version_id: Mapped[int] = mapped_column(ForeignKey("case_versions.id"))
    target: Mapped[str] = mapped_column(String(30), default="MOCK_HR")
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    requested_by: Mapped[str] = mapped_column(String(80))
    review_token: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    receipt: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
