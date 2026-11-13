from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr

from app.demo.generate import picture
from ocr_service.app import Line, OcrOutput, ServiceSettings, create_app


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
        self.model = config.model_name if config else "PP-OCRv6_small"

    def predict(self, path):
        assert path.is_file()
        self.paths.append(path)
        return OcrOutput(model=self.model, lines=[Line(text="EMPLOYEE: MP001", score=0.95)])

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


def test_medium_ocr_service_checks_credentials_before_inference():
    config = ServiceSettings(model_variant="medium", api_token=SecretStr("test-token"))
    runtime = Runtime(config)
    with TestClient(create_app(config, lambda _: runtime)) as client:
        assert client.get("/health").json()["model"] == "PP-OCRv6_medium"
        upload = {"file": ("image.png", picture("MP001", "2026-10-01"))}
        assert client.post("/ocr", files=upload).status_code == 401
        assert client.post("/ocr", files=upload, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert not runtime.paths
        response = client.post("/ocr", files=upload, headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 200 and response.json()["model"] == "PP-OCRv6_medium"


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
