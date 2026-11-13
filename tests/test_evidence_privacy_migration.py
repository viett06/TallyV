"""The PII migration adds state without rewriting evidence or prior analyses."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_privacy_migration_preserves_original_evidence(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/628d41ef2b37_evidence_privacy_gate.py"
    spec = importlib.util.spec_from_file_location("privacy_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE evidence_files (id INTEGER PRIMARY KEY, path TEXT NOT NULL)"))
        db.execute(text("INSERT INTO evidence_files VALUES (1, 'private-original.png')"))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(db)))
        migration.upgrade()
        assert "evidence_privacy" in inspect(db).get_table_names()
        assert db.scalar(text("SELECT path FROM evidence_files WHERE id=1")) == "private-original.png"
        assert db.scalar(text("SELECT count(*) FROM evidence_privacy")) == 0
        migration.downgrade()
        assert "evidence_privacy" not in inspect(db).get_table_names()
        assert db.scalar(text("SELECT path FROM evidence_files WHERE id=1")) == "private-original.png"
    engine.dispose()


def test_retired_ocr_rule_migration_preserves_other_settings_and_history(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/739e52fa3c48_retire_attendance_ocr_rule.py"
    spec = importlib.util.spec_from_file_location("retire_ocr_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    metadata = sa.MetaData()
    rules = sa.Table(
        "demo_rules", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("settings", sa.JSON)
    )
    evidence = sa.Table(
        "evidence_files", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("ocr_text", sa.Text)
    )
    metadata.create_all(engine)
    expected = {"description": "Máy lỗi", "require_shift": False, "version": "existing"}
    with engine.begin() as db:
        db.execute(
            rules.insert(),
            [{"id": 1, "settings": {**expected, "require_readable_ocr": False}}, {"id": 2, "settings": expected}],
        )
        db.execute(evidence.insert(), {"id": 1, "ocr_text": "historical data"})
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(db)))
        migration.upgrade()
        assert db.execute(sa.select(rules.c.settings)).scalars().all() == [expected, expected]
        assert db.scalar(sa.select(evidence.c.ocr_text)) == "historical data"
        migration.downgrade()
        assert all(value["require_readable_ocr"] for value in db.execute(sa.select(rules.c.settings)).scalars())
        assert db.scalar(sa.select(evidence.c.ocr_text)) == "historical data"
    engine.dispose()
