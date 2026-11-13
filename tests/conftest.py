import os

os.environ["SECRET_KEY"] = "test-only-secret-000000000000000000000000"
os.environ["DEMO_PASSWORD"] = "Test-demo-password"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EVIDENCE_VISION_PROVIDER"] = "ollama"
os.environ["EVIDENCE_VISION_CLOUD_MODEL"] = "qwen3-vl-8b-instruct"
os.environ["DASHSCOPE_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["STORAGE_BACKEND"] = "local"
os.environ["ASSISTANT_PROCESSING_MODE"] = "RULE_BASED"
os.environ["ASSISTANT_HYBRID_SHEET_PROVIDER"] = "ollama"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.assistant.config import settings as assistant_settings
from app.core.config import settings
from app.db.base_model import Base
from app.db.session import get_session
from app.demo.catalog import seed
from main import app


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant_settings, "processing_mode", "RULE_BASED")
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "mail_provider", "mailpit")
    monkeypatch.setattr("app.services.image_background.defer", lambda *a, **kw: None)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        seed(db)

    def dependency():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_session] = dependency
    with TestClient(app) as client:
        assert (
            client.post("/api/auth/login", json={"username": "hr.demo", "password": "Test-demo-password"}).status_code
            == 200
        )
        yield sessions, client
    app.dependency_overrides.clear()
    engine.dispose()
