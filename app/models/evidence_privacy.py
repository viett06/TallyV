from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class EvidencePrivacy(Base):
    __tablename__ = "evidence_privacy"
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence_files.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    source_sha256: Mapped[str] = mapped_column(String(64))
    config_revision: Mapped[str] = mapped_column(String(64))
    profile_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str | None] = mapped_column(String(30))
    sanitized_path: Mapped[str | None] = mapped_column(Text)
    sanitized_sha256: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(80), default="")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
