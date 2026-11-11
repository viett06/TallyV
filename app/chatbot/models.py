from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, ForeignKeyConstraint, LargeBinary, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

EMBEDDING_DIMENSIONS = 1024


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    issuer: Mapped[str | None] = mapped_column(String(160))
    document_type: Mapped[str] = mapped_column(String(24), server_default="other")
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    pdf: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    embedding_model: Mapped[str] = mapped_column(String(80))
    page_count: Mapped[int]
    ocr_page_count: Mapped[int]
    chunk_count: Mapped[int]
    published: Mapped[bool] = mapped_column(server_default=false())


class PolicyPage(Base):
    __tablename__ = "policy_pages"

    document_id: Mapped[int] = mapped_column(ForeignKey("policy_documents.id", ondelete="CASCADE"), primary_key=True)
    page_number: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    used_ocr: Mapped[bool]


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ("document_id", "page_number"), ("policy_pages.document_id", "policy_pages.page_number"), ondelete="CASCADE"
        ),
        UniqueConstraint("document_id", "page_number", "start_offset"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int]
    page_number: Mapped[int]
    start_offset: Mapped[int]
    section: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS).with_variant(Text(), "sqlite"))
