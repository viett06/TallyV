from base64 import b64encode
from io import BytesIO
from json import loads
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from pydantic import SecretStr

from app.core.config import settings
from app.services import analysis, gemini
from app.services.evidence_cloud import CloudProviderNotConfigured
from app.services.evidence_vision import Scene, observe


def test_scene_drops_posture_and_position_when_no_person_is_visible():
    scene = Scene(
        kind="WORK_AREA",
        person_visible=False,
        person_at_desk=True,
        posture="SEATED",
        screen_visible=True,
        description="Bàn làm việc có màn hình, không thấy người.",
    )
    assert scene.posture is None
    assert scene.person_at_desk is False and scene.screen_visible is True


def test_vision_only_sends_image_to_internal_ollama(monkeypatch):
    content = b"synthetic image bytes"
    calls = []

    def respond(request):
        calls.append(request)
        scene = Scene(
            kind="WORK_AREA",
            person_visible=True,
            person_at_desk=True,
            posture="SEATED",
            screen_visible=True,
            description="Một người ngồi tại bàn.",
        )
        return httpx.Response(200, json={"message": {"content": scene.model_dump_json()}})

    http_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: http_client(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(settings, "evidence_vision_url", "http://127.0.0.1:11434")
    scene = observe(content)
    assert scene.person_at_desk is True
    assert scene.posture == "SEATED" and scene.screen_visible is True
    (request,) = calls
    assert str(request.url) == "http://127.0.0.1:11434/api/chat"
    assert b64encode(content) in request.content


@pytest.mark.parametrize("provider", ["qwen_cloud", "openrouter"])
def test_cloud_vision_sends_the_image_directly(monkeypatch, provider):
    image = BytesIO()
    Image.new("RGB", (32, 32), "#987abc").save(image, format="PNG")
    content = image.getvalue()
    monkeypatch.setattr(settings, "evidence_vision_provider", provider)
    monkeypatch.setattr(settings, "dashscope_workspace_id", "llm-test")
    requests = []

    def respond(request):
        requests.append(request)
        scene = Scene(
            kind="WORK_AREA",
            person_visible=False,
            person_at_desk=False,
            posture=None,
            screen_visible=True,
            description="Bàn trống có màn hình.",
        )
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": scene.model_dump_json()}}]}
        )

    http_client = httpx.Client

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return http_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    with pytest.raises(ValueError, match="require a PNG"):
        observe(b"invalid image")
    with pytest.raises(CloudProviderNotConfigured):
        observe(content)
    assert requests == []

    api_key_field = "openrouter_api_key" if provider == "openrouter" else "dashscope_api_key"
    monkeypatch.setattr(settings, api_key_field, SecretStr("synthetic-test-key"))
    monkeypatch.setattr(settings, "evidence_vision_enabled", True)
    monkeypatch.setattr(analysis, "read_bytes", lambda _: content)
    evidence = SimpleNamespace(path="private")
    analysis.read_evidence(evidence, {"employee_id": "NV001", "date": "2026-11-09"})
    assert evidence.extracted["vision_status"] == "COMPLETE"
    assert evidence.extracted["scene"]["person_visible"] is False
    (request,) = requests
    assert request.headers["Authorization"] == "Bearer synthetic-test-key"
    payload = loads(request.content)
    if provider == "openrouter":
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert payload["model"] == "qwen/qwen3-vl-8b-instruct"
        assert payload["provider"] == {"only": ["parasail"], "allow_fallbacks": False, "require_parameters": True}
    else:
        assert (
            str(request.url) == "https://llm-test.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
        )
        assert payload["model"] == "qwen3-vl-8b-instruct" and "provider" not in payload
    assert evidence.extracted["vision_model"] == payload["model"]
    assert payload["response_format"] == {"type": "json_object"}
    assert "NV001" not in request.content.decode()
    assert payload["messages"][0]["content"][0]["image_url"]["url"] == (
        "data:image/png;base64," + b64encode(content).decode("ascii")
    )


@pytest.mark.parametrize("provider", ["qwen_cloud", "openrouter"])
def test_invalid_cloud_image_keeps_local_ocr_and_records_unavailable(monkeypatch, provider):
    monkeypatch.setattr(settings, "evidence_vision_provider", provider)
    monkeypatch.setattr(settings, "evidence_vision_enabled", True)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(analysis, "read_bytes", lambda _: b"invalid image")
    monkeypatch.setattr(analysis, "read_text", lambda *a, **kw: "CAMERA 09/11/2026 08:03")
    evidence = SimpleNamespace(path="private")
    analysis.read_evidence(evidence, {"employee_id": "NV001", "date": "2026-11-09"})
    assert evidence.extracted["time"] == "08:03"
    assert evidence.extracted["vision_status"] == "UNAVAILABLE"
    assert "scene" not in evidence.extracted


def test_evidence_preserves_scene_and_ocr_region_but_external_request_uses_only_masked_fields(monkeypatch):
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "evidence_vision_enabled", True)
    monkeypatch.setattr(settings, "processing_mode", "GEMINI")
    monkeypatch.setattr(analysis, "read_bytes", lambda _: b"local image")

    def read_ocr(content, *, regions):
        text = "Mã nhân viên: 007321\n02/10/2026 03:00"
        regions.append({"text": "02/10/2026 03:00", "box": [0.2, 0.3, 0.4, 0.5], "score": 0.95})
        return text

    monkeypatch.setattr(analysis, "read_text", read_ocr)
    monkeypatch.setattr(
        analysis.evidence_vision,
        "observe",
        lambda _: Scene(
            kind="WORK_AREA",
            person_visible=True,
            person_at_desk=True,
            posture="SEATED",
            screen_visible=True,
            description="Nội dung giữ nội bộ",
        ),
    )
    case = {
        "employee_id": "007321",
        "date": "2026-10-01",
        "shift": "22:00–06:00",
        "punch": "",
        "explanation": "Làm ca trực.",
        "name": "Tên Nhân Viên",
    }
    evidence = SimpleNamespace(path="private")
    analysis.read_evidence(evidence, case)
    assert evidence.extracted["ocr_regions"][0]["text"] == "02/10/2026 03:00"
    assert evidence.extracted["scene"]["description"] == "Nội dung giữ nội bộ"
    assert "gemini_comparison" not in evidence.extracted
    payload = gemini.prepare_input(case, [evidence], {})
    attendance_record = payload["case"]["attendance_record"]
    (observed,) = payload["case"]["evidence"]
    assert attendance_record["employee_ref"] == observed["employee_ref"] != "007321"
    assert observed["observed_day_index"] == attendance_record["work_day_index"] + 1
    assert (
        attendance_record["shift_start_index"] < observed["observed_clock_index"] < attendance_record["shift_end_index"]
    )
    assert attendance_record["overnight"] and observed["scene"]["person_at_desk"]
    assert observed["scene"]["posture"] == "SEATED" and observed["scene"]["screen_visible"] is True
    assert "description" not in observed["scene"] and "ocr_regions" not in observed
    assert all(secret not in str(payload) for secret in ("007321", "02/10/2026", "03:00", "Nội dung giữ nội bộ"))
    second = gemini.prepare_input(case, [evidence], {})
    assert second["case"]["attendance_record"]["employee_ref"] != attendance_record["employee_ref"]
    different = gemini.prepare_input({**case, "employee_id": "007322"}, [evidence], {})["case"]
    assert different["attendance_record"]["employee_ref"] != different["evidence"][0]["employee_ref"]
