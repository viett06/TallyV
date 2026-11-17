"""Retire legacy assessment and HR simulator jobs while preserving their history."""

import sqlalchemy as sa

from alembic import op

revision = "34e98d1aa036"
down_revision = "739e52fa3c48"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    jobs = sa.table(
        "processing_jobs",
        sa.column("kind", sa.String),
        sa.column("status", sa.String),
        sa.column("payload", sa.JSON),
        sa.column("error", sa.Text),
        sa.column("locked_at", sa.DateTime(timezone=True)),
    )
    analysis = sa.table(
        "analysis_results",
        sa.column("version_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("extracted", sa.JSON),
        sa.column("error", sa.Text),
    )
    unfinished = jobs.c.status.in_(("PENDING", "RUNNING", "FAILED"))
    legacy_versions = sa.select(jobs.c.payload["version_id"].as_integer()).where(jobs.c.kind == "ANALYZE", unfinished)
    db.execute(
        analysis.update()
        .where(
            analysis.c.version_id.in_(legacy_versions),
            analysis.c.status.in_(("PENDING", "RUNNING")),
            analysis.c.extracted["privacy_request_id"].as_string().is_(None),
        )
        .values(status="NOT_STARTED", error=None)
    )
    retired_reason = "Luồng xử lý mô phỏng đã ngừng hoạt động."
    submissions = sa.table(
        "hr_submissions",
        sa.column("id", sa.String),
        sa.column("status", sa.String),
        sa.column("error", sa.Text),
        sa.column("receipt", sa.JSON),
        sa.column("applied_at", sa.DateTime(timezone=True)),
    )
    receipts = sa.table(
        "mock_hr_receipts",
        sa.column("id", sa.String),
        sa.column("record_id", sa.String),
        sa.column("before", sa.JSON),
        sa.column("after", sa.JSON),
        sa.column("source", sa.JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    # The former HTTP service could commit a receipt before the worker recorded it.
    accepted = (
        db.execute(
            sa.select(receipts)
            .join(submissions, submissions.c.id == receipts.c.id)
            .where(submissions.c.status.in_(("QUEUED", "FAILED")))
        )
        .mappings()
        .all()
    )
    for receipt in accepted:
        created_at = receipt["created_at"]
        db.execute(
            submissions.update()
            .where(submissions.c.id == receipt["id"])
            .values(
                status="APPLIED",
                error=None,
                applied_at=created_at,
                receipt={**receipt, "created_at": created_at.isoformat()},
            )
        )
    db.execute(
        submissions.update().where(submissions.c.status == "QUEUED").values(status="CANCELLED", error=retired_reason)
    )
    db.execute(
        jobs.update()
        .where(jobs.c.kind.in_(("ANALYZE", "INDEX_EVIDENCE", "HR_SUBMIT")), unfinished)
        .values(status="CANCELLED", locked_at=None, error="Tác vụ cũ đã ngừng hoạt động.")
    )


def downgrade():
    # Restoring the old code must never replay previously retired work.
    pass
