"""Vision transport accepts sanitized images only, for the attendance provider."""

from base64 import b64encode
from json import loads

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services.evidence_masking import ProfileSet, process
from app.services.evidence_vision import infer
from tests.test_evidence_vlm import profile, sample


def test_original_and_layout_only_images_never_reach_vlm(monkeypatch):
    preview = process(sample(), ProfileSet(profiles=[profile()])).image
    monkeypatch.setattr(httpx, "Client", lambda **kw: pytest.fail("Images without OCR must never reach HTTP"))
    for image in (sample(), preview):
        with pytest.raises(ValueError):
            infer([image], "unsafe", {})


def test_provider_transports_only_processed_pixels(monkeypatch):
    image = process(sample(), ProfileSet(profiles=[profile()]), detect_text=lambda _: []).image
    reply = '{"status":"complete"}'
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": reply}}]})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("synthetic"))
    assert infer([image], "Describe safe evidence", {}) == reply
    assert len(requests) == 1 and b64encode(image.content) in requests[0].content
    assert b64encode(sample()) not in requests[0].content
    body = loads(requests[0].content)
    assert body["provider"]["allow_fallbacks"] is False
