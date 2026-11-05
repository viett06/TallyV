"""Exercise file intake, private downloads, OCR and migration through S3 storage."""

import hashlib
from uuid import uuid4

import boto3
import httpx
import pytest
from botocore.exceptions import EndpointConnectionError
from moto import mock_aws
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import AppError
from app.demo.generate import picture, workbook
from app.models import Attachment, CaseVersion, EvidenceFile
from app.services import storage
from app.services.analysis import analyze
from scripts.configure_storage import configure
from scripts.migrate_storage import migrate_files
from tests.helpers import ingest, row
from tests.test_ocr_service import configure_http


@pytest.fixture
def s3(context, monkeypatch):
    with mock_aws():
        client = boto3.client(
            "s3", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing"
        )
        client.create_bucket(Bucket="tallyv-files")
        monkeypatch.setattr(settings, "storage_backend", "s3")
        monkeypatch.setattr(settings, "s3_bucket", "tallyv-files")
        monkeypatch.setattr(settings, "s3_prefix", "tallyv/")
        monkeypatch.setattr(storage, "_s3_client", lambda *args: client)
        yield client, storage.get_s3_storage()


def test_s3_excel_intake_download_and_ocr_without_local_copies(context, s3, monkeypatch):
    sessions, client = context
    s3_client, _ = s3
    image = picture("MP001", "2026-10-01")
    excel = workbook([row()], {2: [image]})
    calls = []

    def handler(request):
        assert image in request.read()
        calls.append(request.url.path)
        return httpx.Response(200, json={"lines": [{"text": "MP001 2026-10-01 RECORDED", "score": 0.99}]})

    configure_http(monkeypatch, handler)
    with sessions() as db:
        ingest(db, excel)
        analyze(db, db.scalar(select(CaseVersion.id)))
        evidence = db.scalar(select(EvidenceFile))
        attachment = db.scalar(select(Attachment))
        assert evidence.ocr_status == "READABLE"
        evidence_id, attachment_id = evidence.id, attachment.id
        names = [evidence.path, attachment.path]
        db.commit()
    assert calls == ["/ocr"]
    assert client.get(f"/api/evidence/{evidence_id}").content == image
    response = client.get(f"/api/attachments/{attachment_id}")
    assert response.content == excel
    assert "no-store" in response.headers["cache-control"]
    assert list(settings.storage_dir.iterdir()) == []
    assert s3_client.list_objects_v2(Bucket="tallyv-files", Prefix="tallyv/")["KeyCount"] == 2
    for name in names:
        assert s3_client.head_object(Bucket="tallyv-files", Key="tallyv/" + name)["Metadata"]["sha256"]
    client.cookies.clear()
    assert client.get(f"/api/evidence/{evidence_id}").status_code == 401


def test_s3_missing_or_failed_storage_does_not_fall_back_to_local(context, s3, monkeypatch):
    client, _ = s3
    name = uuid4().hex + ".png"
    storage.LocalStorage(settings.storage_dir).write(name, b"local copy")
    with pytest.raises(AppError) as missing:
        storage.read_bytes(name)
    assert missing.value.status_code == 404

    def unavailable(**kwargs):
        raise EndpointConnectionError(endpoint_url="http://private-storage")

    monkeypatch.setattr(client, "get_object", unavailable)
    with pytest.raises(AppError) as failed:
        storage.read_bytes(name)
    assert failed.value.status_code == 503
    assert "private-storage" not in str(failed.value)
    monkeypatch.setattr(client, "put_object", unavailable)
    with pytest.raises(AppError) as failed_write:
        storage.store_bytes(b"new", ".png")
    assert failed_write.value.status_code == 503
    assert len(list(settings.storage_dir.iterdir())) == 1


@pytest.mark.parametrize("name", ["../secret", "/tmp/secret", "https://host/file", "x.png", "a" * 32 + ".exe"])
def test_storage_rejects_non_owned_paths(context, name):
    with pytest.raises(ValueError):
        storage.read_bytes(name)


def test_migration_is_verified_repeatable_and_preserves_local_data(context, s3):
    client, target = s3
    name = uuid4().hex + ".bin"
    content = b"original workbook content"
    local = storage.LocalStorage(settings.storage_dir)
    local.write(name, content)
    records = [(name, hashlib.sha256(content).hexdigest())]
    result = migrate_files(records, settings.storage_dir, target)
    assert result["dry_run"] and not client.list_objects_v2(Bucket="tallyv-files").get("Contents")
    assert migrate_files(records, settings.storage_dir, target, apply=True)["copied"] == 1
    assert target.read(name) == local.read(name) == content
    assert migrate_files(records, settings.storage_dir, target, apply=True)["already_verified"] == 1
    target.write(name, b"conflicting remote content")
    with pytest.raises(ValueError, match="Remote checksum mismatch"):
        migrate_files(records, settings.storage_dir, target, apply=True)
    assert target.read(name) == b"conflicting remote content"


def test_migration_checks_all_sources_before_writing(context, s3):
    client, target = s3
    names = [uuid4().hex + ".png" for _ in range(2)]
    local = storage.LocalStorage(settings.storage_dir)
    for name in names:
        local.write(name, b"data")
    records = [(names[0], hashlib.sha256(b"data").hexdigest()), (names[1], "invalid hash")]
    with pytest.raises(ValueError, match="Local checksum mismatch"):
        migrate_files(records, settings.storage_dir, target, apply=True)
    assert not client.list_objects_v2(Bucket="tallyv-files").get("Contents")


def test_storage_setup_preserves_credentials_and_requires_explicit_activation(tmp_path):
    path = tmp_path / ".env"
    path.write_text("SECRET_KEY=existing-secret\nMAIL_PROVIDER=outlook\n")
    configure(path)
    first = path.read_text()
    assert "STORAGE_BACKEND=local" in first
    configure(path)
    assert path.read_text() == first
    configure(path, activate=True)
    assert path.read_text() == first.replace("STORAGE_BACKEND=local", "STORAGE_BACKEND=s3")
    assert path.stat().st_mode & 0o777 == 0o600
