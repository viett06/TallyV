from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.attendance import SHEET_NAME
from app.core.time import utcnow
from app.db.base import Base


class CaseVersion(Base):
    __tablename__ = "case_versions"
    __table_args__ = (UniqueConstraint("case_id", "fingerprint"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("attendance_cases.id"))
    attachment_id: Mapped[int] = mapped_column(ForeignKey("attachments.id"))
    sheet: Mapped[str] = mapped_column(String(100), default=SHEET_NAME)
    row_number: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    raw: Mapped[dict] = mapped_column(JSON)
    normalized: Mapped[dict] = mapped_column(JSON)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
