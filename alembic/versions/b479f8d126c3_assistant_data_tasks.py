"""Add durable Assistant task execution and confirmed classification rules.

Revision ID: b479f8d126c3
Revises: a368e7c015b2
"""

import sqlalchemy as sa

from alembic import op

revision = "b479f8d126c3"
down_revision = "a368e7c015b2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assistant_generation_runs") as batch:
        batch.add_column(sa.Column("kind", sa.String(20), nullable=False, server_default="DOCUMENT"))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("parent_run_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("state", sa.JSON(), nullable=False, server_default="{}"))
        batch.create_foreign_key("fk_assistant_run_parent", "assistant_generation_runs", ["parent_run_id"], ["id"])
    op.create_table(
        "assistant_task_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("assistant_generation_runs.id"), nullable=False),
        sa.Column("step_id", sa.String(80), nullable=False),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "step_id"),
    )
    op.create_index("ix_assistant_task_steps_run_id", "assistant_task_steps", ["run_id"])
    op.create_table(
        "assistant_business_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_column", sa.String(160), nullable=False),
        sa.Column("source_value", sa.String(1000), nullable=False),
        sa.Column("category", sa.String(160), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("assistant_generation_runs.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assistant_business_rules_user_id", "assistant_business_rules", ["user_id"])


def downgrade():
    op.drop_index("ix_assistant_business_rules_user_id", "assistant_business_rules")
    op.drop_table("assistant_business_rules")
    op.drop_index("ix_assistant_task_steps_run_id", "assistant_task_steps")
    op.drop_table("assistant_task_steps")
    with op.batch_alter_table("assistant_generation_runs") as batch:
        batch.drop_constraint("fk_assistant_run_parent", type_="foreignkey")
        for column in ("state", "parent_run_id", "revision", "kind"):
            batch.drop_column(column)
