from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class AttendanceCase(Base):
    __tablename__ = "attendance_cases"
    __table_args__ = (Index("ix_attendance_cases_period_cycle", "period_id", "cycle_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    period_id: Mapped[str] = mapped_column(ForeignKey("review_periods.id"))
    cycle_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    active_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_status: Mapped[str] = mapped_column(String(30), default="PENDING_REVIEW")
    hr_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    hr_note: Mapped[str] = mapped_column(Text, default="")
    confirmed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
