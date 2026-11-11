"""Add policy PDF ingestion with page provenance and pgvector embeddings."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "f821446ec9e2"
down_revision = "0f0ce74db521"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("pdf", sa.LargeBinary(), nullable=False),
        sa.Column("embedding_model", sa.String(80), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("ocr_page_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "policy_pages",
        sa.Column(
            "document_id", sa.Integer(), sa.ForeignKey("policy_documents.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("page_number", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("used_ocr", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "policy_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024).with_variant(sa.Text(), "sqlite"), nullable=False),
        sa.ForeignKeyConstraint(
            ("document_id", "page_number"), ("policy_pages.document_id", "policy_pages.page_number"), ondelete="CASCADE"
        ),
        sa.UniqueConstraint("document_id", "page_number", "start_offset"),
    )


def downgrade():
    op.drop_table("policy_chunks")
    op.drop_table("policy_pages")
    op.drop_table("policy_documents")
