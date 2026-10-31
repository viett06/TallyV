from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (UniqueConstraint("email_id", "part_index"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"))
    part_index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
