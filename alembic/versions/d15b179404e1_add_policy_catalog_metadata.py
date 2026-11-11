"""Add optional document titles and filters for the employee library."""

import sqlalchemy as sa

from alembic import op

revision = "d15b179404e1"
down_revision = "a63e2d9f4701"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("policy_documents", sa.Column("title", sa.String(255)))
    op.add_column("policy_documents", sa.Column("issuer", sa.String(160)))
    op.add_column("policy_documents", sa.Column("document_type", sa.String(24), nullable=False, server_default="other"))


def downgrade():
    op.drop_column("policy_documents", "document_type")
    op.drop_column("policy_documents", "issuer")
    op.drop_column("policy_documents", "title")
