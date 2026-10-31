"""One Microsoft 365 inbox per workspace; credentials never leave the backend."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutlookConnection(Base):
    __tablename__ = "outlook_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    transport: Mapped[str] = mapped_column(String(20), default="microsoft", server_default="microsoft")
    status: Mapped[str] = mapped_column(String(30), default="DISCONNECTED")
    mailbox: Mapped[str] = mapped_column(String(320), default="")
    mailbox_id: Mapped[str] = mapped_column(String(100), default="")
    account_id: Mapped[str] = mapped_column(String(255), default="")
    token_cache: Mapped[str] = mapped_column(Text, default="")
    delta_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutlookAuthFlow(Base):
    __tablename__ = "outlook_auth_flows"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
