from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("case_versions.id"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    category: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    reason: Mapped[str] = mapped_column(Text, default="")
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    missing: Mapped[list] = mapped_column(JSON, default=list)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    evidence_checks: Mapped[list] = mapped_column(JSON, default=list)
    assessment: Mapped[str] = mapped_column(String(30), default="MISSING")
    method: Mapped[str] = mapped_column(String(30), default="RULE_BASED")
    rules_version: Mapped[str] = mapped_column(String(30), default="demo-1.0")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
