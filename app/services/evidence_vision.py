"""Transport for privacy-approved visual assessments."""

from base64 import b64encode
from json import dumps

import httpx

from app.core.config import settings
from app.services.evidence_masking import SanitizedImage

MODEL_ID = "qwen/qwen3-vl-8b-instruct"


class VisionProviderNotConfigured(ValueError):
    """The selected vision provider has no credentials."""


def infer(images: list[SanitizedImage], prompt: str, schema: dict, *, max_tokens: int = 2048) -> str:
    """Infer over locally redacted images. Callers validate the structured result."""
    if not images or len(images) > 10 or any(not isinstance(item, SanitizedImage) for item in images):
        raise ValueError("Expected 1 to 10 redacted images")
    for item in images:
        if not item.content.startswith(b"\x89PNG\r\n\x1a\n") or len(item.content) > 8 * 1024 * 1024:
            raise ValueError("VLM requires a PNG within the evidence size limit")
    prompt = f"{prompt}\nTrả về JSON theo schema sau: {dumps(schema, ensure_ascii=False)}"
    key = settings.openrouter_api_key.get_secret_value().strip()
    if not key:
        raise VisionProviderNotConfigured()
    with httpx.Client(timeout=httpx.Timeout(90, connect=5), trust_env=False, follow_redirects=False) as client:
        response = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": MODEL_ID,
                "provider": {"only": ["parasail"], "allow_fallbacks": False, "require_parameters": True},
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64encode(item.content).decode('ascii')}"
                                },
                            }
                            for item in images
                        ]
                        + [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
            },
        )
        response.raise_for_status()
    choice = response.json()["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("VLM did not complete the assessment")
    return choice["message"]["content"]
