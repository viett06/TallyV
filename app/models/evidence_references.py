from sqlalchemy import JSON, Boolean, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvidenceViewpoint(Base):
    __tablename__ = "evidence_viewpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    location: Mapped[str | None] = mapped_column(String(160))
    location_basis: Mapped[str | None] = mapped_column(String(320))
    location_evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_files.id", ondelete="SET NULL"))


class EvidenceReference(Base):
    __tablename__ = "evidence_references"
    __table_args__ = (Index("ix_evidence_references_model", "model"),)

    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence_files.id", ondelete="CASCADE"), primary_key=True)
    viewpoint_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_viewpoints.id", ondelete="SET NULL"))
    model: Mapped[str] = mapped_column(String(100))
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
