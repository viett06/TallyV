"""Support manual attendance cases and retain deleted case history."""

import sqlalchemy as sa

from alembic import op

revision = "0f0ce74db521"
down_revision = "b479f8d126c3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("attendance_cases", sa.Column("manual_source", sa.String(20), nullable=True))
    op.add_column("attendance_cases", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("case_versions") as batch:
        batch.alter_column("attachment_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table("case_versions") as batch:
        batch.alter_column("attachment_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("attendance_cases", "deleted_at")
    op.drop_column("attendance_cases", "manual_source")
