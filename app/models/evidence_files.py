from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("case_versions.id"))
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    anchor: Mapped[str] = mapped_column(String(80))
    ocr_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    checks: Mapped[list] = mapped_column(JSON, default=list)
