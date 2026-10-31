from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewPeriod(Base):
    __tablename__ = "review_periods"
    id: Mapped[str] = mapped_column(String(7), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    starts: Mapped[date] = mapped_column(Date)
    ends: Mapped[date] = mapped_column(Date)
