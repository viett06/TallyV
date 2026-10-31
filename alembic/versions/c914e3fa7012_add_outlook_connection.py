"""Store encrypted Microsoft delegated authentication and a durable inbox cursor.

Revision ID: c914e3fa7012
Revises: b703d8a21c45
"""

import sqlalchemy as sa

from alembic import op

revision = "c914e3fa7012"
down_revision = "b703d8a21c45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outlook_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("mailbox", sa.String(320), nullable=False),
        sa.Column("mailbox_id", sa.String(100), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("token_cache", sa.Text(), nullable=False),
        sa.Column("delta_link", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "outlook_auth_flows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("outlook_auth_flows")
    op.drop_table("outlook_connections")
