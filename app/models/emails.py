from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (Index("ix_emails_period_cycle", "period_id", "cycle_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), unique=True)
    message_id: Mapped[str | None] = mapped_column(String(300), unique=True, nullable=True)
    sender: Mapped[str] = mapped_column(String(200))
    recipient: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    period_id: Mapped[str | None] = mapped_column(ForeignKey("review_periods.id"), nullable=True)
    cycle_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
