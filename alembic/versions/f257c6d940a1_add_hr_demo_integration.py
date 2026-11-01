"""Add durable correction requests and HTTP HR simulator storage.

Revision ID: f257c6d940a1
Revises: e146b20a9c73
"""

import sqlalchemy as sa

from alembic import op

revision = "f257c6d940a1"
down_revision = "e146b20a9c73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("attendance_cases.id"), nullable=False),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("case_versions.id"), nullable=False),
        sa.Column("target", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("requested_by", sa.String(80), nullable=False),
        sa.Column("review_token", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_hr_submissions_case_created", "hr_submissions", ["case_id", "created_at"])
    op.create_table(
        "mock_hr_attendance",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("employee_id", sa.String(60), nullable=False),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("department", sa.String(200), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("shift", sa.String(200), nullable=False),
        sa.Column("check_in", sa.String(5), nullable=True),
        sa.Column("check_out", sa.String(5), nullable=True),
        sa.Column("day_status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "employee_id", "work_date", "shift"),
    )
    op.create_table(
        "mock_hr_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("record_id", sa.String(64), sa.ForeignKey("mock_hr_attendance.id"), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mock_hr_receipts")
    op.drop_table("mock_hr_attendance")
    op.drop_index("ix_hr_submissions_case_created", table_name="hr_submissions")
    op.drop_table("hr_submissions")
