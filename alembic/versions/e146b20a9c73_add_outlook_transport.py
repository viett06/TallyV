"""Identify Microsoft-direct and Composio MVP mailbox connections.

Revision ID: e146b20a9c73
Revises: d035a91e7b62
"""

import sqlalchemy as sa

from alembic import op

revision = "e146b20a9c73"
down_revision = "d035a91e7b62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outlook_connections",
        sa.Column("transport", sa.String(20), nullable=False, server_default="microsoft"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT COUNT(*) FROM outlook_connections WHERE transport <> 'microsoft' AND status <> 'DISCONNECTED'")
    ).scalar_one():
        raise RuntimeError("Disconnect Composio before removing mailbox transport support")
    op.drop_column("outlook_connections", "transport")
