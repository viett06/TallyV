"""Tables owned by the HTTP HR simulator, not SAP standard tables."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class MockHrAttendance(Base):
    __tablename__ = "mock_hr_attendance"
    __table_args__ = (UniqueConstraint("source", "employee_id", "work_date", "shift"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    employee_id: Mapped[str] = mapped_column(String(60))
    employee_name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(200))
    work_date: Mapped[date] = mapped_column(Date)
    shift: Mapped[str] = mapped_column(String(200))
    check_in: Mapped[str | None] = mapped_column(String(5), nullable=True)
    check_out: Mapped[str | None] = mapped_column(String(5), nullable=True)
    day_status: Mapped[str] = mapped_column(String(20), default="PRESENT")
    revision: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MockHrReceipt(Base):
    __tablename__ = "mock_hr_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("mock_hr_attendance.id"))
    request_hash: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    source: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
