"""Track explicit weekly review cycles without guessing historical assignments.

Revision ID: a6c832f03190
Revises: 305ed758b40c
"""

import sqlalchemy as sa

from alembic import op

revision = "a6c832f03190"
down_revision = "305ed758b40c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("emails", "attendance_cases"):
        op.add_column(table, sa.Column("cycle_start", sa.Date(), nullable=True))
        op.create_index(f"ix_{table}_period_cycle", table, ["period_id", "cycle_start"])


def downgrade() -> None:
    for table in ("attendance_cases", "emails"):
        op.drop_index(f"ix_{table}_period_cycle", table_name=table)
        op.drop_column(table, "cycle_start")
