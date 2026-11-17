import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db.base_model import Base
from app.models import AnalysisResult, HrSubmission, MockHrReceipt, ProcessingJob


def test_retire_legacy_jobs_preserves_current_jobs_and_historical_receipts(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/34e98d1aa036_retire_legacy_jobs.py"
    spec = importlib.util.spec_from_file_location("retire_legacy_jobs", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    jobs = ProcessingJob.__table__
    analysis = AnalysisResult.__table__
    submissions = HrSubmission.__table__
    receipts = MockHrReceipt.__table__
    with engine.begin() as db:
        db.execute(
            jobs.insert(),
            [
                {"kind": kind, "key": key, "status": status, "payload": payload}
                for kind, key, status, payload in [
                    ("ANALYZE", "legacy", "RUNNING", {"version_id": 1}),
                    ("ANALYZE", "newer", "FAILED", {"version_id": 2}),
                    ("INDEX_EVIDENCE", "index", "PENDING", {"version_id": 1}),
                    ("HR_SUBMIT", "hr", "PENDING", {}),
                    ("IMPORT_EMAIL", "import", "PENDING", {}),
                    ("ASSISTANT_GENERATE", "assistant", "PENDING", {}),
                    ("ANALYZE", "history", "DONE", {"version_id": 3}),
                ]
            ],
        )
        db.execute(
            analysis.insert(),
            [
                {"version_id": 1, "status": "RUNNING", "extracted": {"historical": True}},
                {"version_id": 2, "status": "PENDING", "extracted": {"privacy_request_id": "current"}},
                {"version_id": 3, "status": "COMPLETED", "extracted": {}},
            ],
        )
        db.execute(
            submissions.insert(),
            [
                {
                    "id": name,
                    "case_id": 1,
                    "version_id": 1,
                    "requested_by": "test",
                    "review_token": "test",
                    "payload": {},
                }
                for name in ("unapplied", "accepted")
            ],
        )
        db.execute(
            receipts.insert().values(
                id="accepted",
                record_id="sample",
                request_hash="test",
                before={},
                after={"revision": 2},
                source={},
                created_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
            )
        )

        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(db)))
        migration.upgrade()

        assert {key: status for key, status in db.execute(sa.select(jobs.c.key, jobs.c.status))} == {
            "legacy": "CANCELLED",
            "newer": "CANCELLED",
            "index": "CANCELLED",
            "hr": "CANCELLED",
            "import": "PENDING",
            "assistant": "PENDING",
            "history": "DONE",
        }
        assert {key: status for key, status in db.execute(sa.select(analysis.c.version_id, analysis.c.status))} == {
            1: "NOT_STARTED",
            2: "PENDING",
            3: "COMPLETED",
        }
        saved = db.execute(sa.select(submissions).order_by(submissions.c.id)).mappings().all()
        assert saved[0]["status"] == "APPLIED" and saved[0]["receipt"]["after"] == {"revision": 2}
        assert saved[1]["status"] == "CANCELLED"
        assert db.scalar(sa.select(receipts.c.id)) == "accepted"
    engine.dispose()
