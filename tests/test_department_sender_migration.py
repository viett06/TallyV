"""Prove that upgrading sender cardinality preserves existing department mappings."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_migration_preserves_existing_addresses_and_refuses_lossy_downgrade(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/d035a91e7b62_add_department_senders.py"
    spec = importlib.util.spec_from_file_location("sender_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.execute(
            text(
                "CREATE TABLE departments (id INTEGER PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL, sender VARCHAR(120) UNIQUE NOT NULL)"
            )
        )
        db.execute(
            text("INSERT INTO departments VALUES (1,'Test One','ONE@example.test'),(2,'Test Two','two@example.test')")
        )
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(db)))
        migration.upgrade()
        assert db.execute(
            text("SELECT department_id,address FROM department_senders ORDER BY department_id")
        ).all() == [(1, "one@example.test"), (2, "two@example.test")]
        assert "sender" not in {column["name"] for column in inspect(db).get_columns("departments")}
        db.execute(text("INSERT INTO department_senders VALUES (1,'another@example.test')"))
        with pytest.raises(RuntimeError, match="one unique sender"):
            migration.downgrade()
        assert db.scalar(text("SELECT count(*) FROM department_senders")) == 3
        db.execute(text("DELETE FROM department_senders WHERE address='another@example.test'"))
        migration.downgrade()
        assert db.execute(text("SELECT id,sender FROM departments ORDER BY id")).all() == [
            (1, "one@example.test"),
            (2, "two@example.test"),
        ]
    engine.dispose()
