"""Vision transport accepts sanitized images only, across every provider."""

from base64 import b64encode
from json import loads

import httpx
import pytest
from pydantic import SecretStr
from tallyv_image_preprocessing import ProfileSet, process

from app.core.config import settings
from app.services.evidence_vision import infer
from tests.test_evidence_vlm import profile, sample


@pytest.mark.parametrize("provider", ["ollama", "openrouter", "qwen_cloud"])
def test_raw_images_are_rejected_before_every_vision_provider(monkeypatch, provider):
    monkeypatch.setattr(settings, "evidence_vision_provider", provider)
    monkeypatch.setattr(httpx, "Client", lambda **kw: pytest.fail("Raw bytes must never reach HTTP"))
    with pytest.raises(ValueError):
        infer([sample()], "unsafe", {})


@pytest.mark.parametrize("provider", ["ollama", "openrouter", "qwen_cloud"])
def test_provider_transports_only_processed_pixels(monkeypatch, provider):
    image = process(sample(), ProfileSet(profiles=[profile()])).image
    reply = '{"status":"complete"}'
    requests = []

    def handler(request):
        requests.append(request)
        if provider == "ollama":
            return httpx.Response(200, json={"done": True, "done_reason": "stop", "message": {"content": reply}})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": reply}}]})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(settings, "evidence_vision_provider", provider)
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("synthetic"))
    monkeypatch.setattr(settings, "dashscope_api_key", SecretStr("synthetic"))
    assert infer([image], "Describe safe evidence", {}) == reply
    assert len(requests) == 1 and b64encode(image.content) in requests[0].content
    assert b64encode(sample()) not in requests[0].content
    body = loads(requests[0].content)
    if provider == "openrouter":
        assert body["provider"]["allow_fallbacks"] is False
