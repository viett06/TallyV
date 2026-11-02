from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings, settings
from app.demo.generate import picture, workbook
from app.models import AnalysisResult, CaseVersion, EvidenceFile
from app.services.analysis import analyze
from ocr_service.app import Line, OcrOutput, ServiceSettings, create_app
from tests.helpers import ingest, row


def test_service_configuration_uses_its_own_environment_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SERVICE_MODELS_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_SERVICE_CPU_THREADS", "2")
    monkeypatch.setenv("OCR_ENABLED", "false")
    config = ServiceSettings.from_env()
    assert config.models_dir == tmp_path and config.cpu_threads == 2


class Runtime:
    def __init__(self, config):
        self.paths = []
        self.closed = False

    def predict(self, path):
        assert path.is_file()
        self.paths.append(path)
        return OcrOutput(lines=[Line(text="EMPLOYEE: MP001", score=0.95)])

    def close(self):
        self.closed = True


def test_service_loads_once_reuses_model_and_removes_request_files():
    instances = []

    def factory(config):
        runtime = Runtime(config)
        instances.append(runtime)
        return runtime

    with TestClient(create_app(runtime_factory=factory)) as client:
        assert client.get("/health").json()["status"] == "ready"
        for _ in range(2):
            response = client.post("/ocr", files={"file": ("../../private.png", picture("MP001", "2026-10-01"))})
            assert response.status_code == 200
            assert response.json() == {
                "model": "PP-OCRv6_small",
                "lines": [{"text": "EMPLOYEE: MP001", "score": 0.95}],
            }
        assert len(instances) == 1 and len(instances[0].paths) == 2
        assert all(not path.exists() for path in instances[0].paths)
        assert not instances[0].closed
    assert instances[0].closed


def test_service_rejects_invalid_images_and_limits_before_inference():
    runtime = Runtime(None)
    config = ServiceSettings(max_upload_bytes=10000, max_image_pixels=100)
    gif = BytesIO()
    Image.new("RGB", (1, 1)).save(gif, format="GIF")
    large_image = BytesIO()
    Image.new("RGB", (11, 10)).save(large_image, format="PNG")
    with TestClient(create_app(config, lambda _: runtime)) as client:
        for content, expected_status in [
            (b"not an image", 400),
            (b"x" * 10001, 413),
            (gif.getvalue(), 415),
            (large_image.getvalue(), 413),
        ]:
            assert client.post("/ocr", files={"file": ("image.png", content)}).status_code == expected_status
    assert not runtime.paths


def test_service_model_error_has_no_image_text_or_internal_details():
    class BrokenRuntime(Runtime):
        def predict(self, path):
            self.paths.append(path)
            raise RuntimeError("private recognized text and internal path")

    runtime = BrokenRuntime(None)
    with TestClient(create_app(runtime_factory=lambda _: runtime)) as client:
        response = client.post("/ocr", files={"file": ("sample.png", picture("MP001", "2026-10-01"))})
        assert response.status_code == 503
        assert response.json() == {"detail": "OCR inference unavailable"}
    assert not runtime.paths[0].exists() and runtime.closed


def configure_http(monkeypatch, handler):
    original_client = httpx.Client

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "ocr_backend", "http")
    monkeypatch.setattr(settings, "ocr_api_url", "http://127.0.0.1:8001")
    monkeypatch.setattr("app.services.ocr.httpx.Client", client)


def test_tallyv_posts_image_and_uses_http_text_for_existing_conflict_checks(context, monkeypatch):
    sessions, _ = context
    image = picture("MP001", "2026-10-01")
    texts = ["EMPLOYEE: MPOO1", "DATE: 2026-10-02", "STATUS: RECORDED"]

    def handler(request):
        assert request.method == "POST" and str(request.url) == "http://127.0.0.1:8001/ocr"
        assert request.headers["content-type"].startswith("multipart/form-data;")
        body = request.read()
        assert b'name="file"' in body and image in body
        assert b"/Users/" not in body and b"/app/data" not in body
        return httpx.Response(200, json={"lines": [{"text": text, "score": 0.95} for text in texts]})

    configure_http(monkeypatch, handler)
    with sessions() as db:
        ingest(db, workbook([row()], {2: [image]}))
        analyze(db, db.scalar(select(CaseVersion.id)))
        evidence = db.scalar(select(EvidenceFile))
        result = db.scalar(select(AnalysisResult))
        assert evidence.ocr_text == "\n".join(texts)
        assert evidence.ocr_status == "READABLE"
        assert evidence.extracted["employee_id"] == "MP001" and "normalization" in evidence.extracted
        assert evidence.extracted["date"] == "2026-10-02"
        assert result.assessment == "CONFLICT"


@pytest.mark.parametrize("failure", ["timeout", "unavailable", "redirect", "bad_json", "bad_schema", "bad_score"])
def test_http_failure_clears_stale_evidence_without_tesseract_fallback(context, monkeypatch, failure):
    import pytesseract

    sessions, _ = context
    calls = []
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *a, **k: calls.append("tesseract"))

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private upstream details", request=request)
        if failure == "unavailable":
            return httpx.Response(503, json={"detail": "private upstream details"})
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "https://outside.invalid/ocr"})
        if failure == "bad_json":
            return httpx.Response(200, content=b"not JSON")
        if failure == "bad_schema":
            return httpx.Response(200, json={"text": "unvalidated text"})
        return httpx.Response(200, json={"lines": [{"text": "MP001", "score": 1.5}]})

    configure_http(monkeypatch, handler)
    with sessions() as db:
        ingest(db, workbook([row()], {2: [picture("MP001", "2026-10-01")]}))
        evidence = db.scalar(select(EvidenceFile))
        evidence.ocr_text = "stale text"
        evidence.extracted = {"employee_id": "MP001"}
        analyze(db, db.scalar(select(CaseVersion.id)))
        result = db.scalar(select(AnalysisResult))
        assert evidence.ocr_status == "UNAVAILABLE" and evidence.ocr_text == "" and evidence.extracted == {}
        assert result.assessment == "MISSING"
        assert "private upstream details" not in str(evidence.checks)
    assert calls == []


def test_empty_successful_http_result_is_unreadable_not_unavailable(context, monkeypatch):
    configure_http(monkeypatch, lambda request: httpx.Response(200, json={"lines": []}))
    sessions, _ = context
    with sessions() as db:
        ingest(db, workbook([row()], {2: [picture("MP001", "2026-10-01")]}))
        analyze(db, db.scalar(select(CaseVersion.id)))
        evidence = db.scalar(select(EvidenceFile))
        assert evidence.ocr_status == "UNREADABLE" and evidence.ocr_text == ""


@pytest.mark.parametrize(
    "url",
    [
        "https://public.example.com",
        "http://public.example.com",
        "http://user:secret@127.0.0.1:8001",
        "http://127.0.0.1?x=1",
    ],
)
def test_ocr_settings_reject_external_endpoints_and_credentials(url):
    with pytest.raises(ValidationError):
        Settings(ocr_api_url=url)
