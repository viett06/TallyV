"""Allow HR to publish policy documents to the employee portal."""

import sqlalchemy as sa

from alembic import op

revision = "a63e2d9f4701"
down_revision = "f821446ec9e2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("policy_documents", sa.Column("published", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    op.drop_column("policy_documents", "published")
