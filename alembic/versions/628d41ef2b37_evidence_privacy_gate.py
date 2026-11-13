"""Persist offline PII processing separately from AI analysis."""

import sqlalchemy as sa

from alembic import op

revision = "628d41ef2b37"
down_revision = "517c8e3a42bf"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_privacy",
        sa.Column("evidence_id", sa.Integer(), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("config_revision", sa.String(64), nullable=False),
        sa.Column("profile_id", sa.String(64)),
        sa.Column("kind", sa.String(30)),
        sa.Column("sanitized_path", sa.Text()),
        sa.Column("sanitized_sha256", sa.String(64)),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("evidence_privacy")
