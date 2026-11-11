"""Store image references and viewpoint labels for attendance evidence."""

import sqlalchemy as sa

from alembic import op

revision = "517c8e3a42bf"
down_revision = "d15b179404e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_viewpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location", sa.String(160)),
        sa.Column("location_basis", sa.String(320)),
        sa.Column("location_evidence_id", sa.Integer(), sa.ForeignKey("evidence_files.id", ondelete="SET NULL")),
    )
    op.create_table(
        "evidence_references",
        sa.Column(
            "evidence_id", sa.Integer(), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("viewpoint_id", sa.Integer(), sa.ForeignKey("evidence_viewpoints.id", ondelete="SET NULL")),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("embedding", sa.JSON()),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_evidence_references_model", "evidence_references", ["model"])


def downgrade():
    op.drop_table("evidence_references")
    op.drop_table("evidence_viewpoints")
