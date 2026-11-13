"""Transport for privacy-approved visual assessments."""

from base64 import b64encode
from json import dumps

import httpx
from tallyv_image_preprocessing import SanitizedImage

from app.core.config import settings

OPENROUTER_VISION_MODEL = "qwen/qwen3-vl-8b-instruct"


class VisionProviderNotConfigured(ValueError):
    """The selected vision provider has no credentials."""


def model_id() -> str:
    return {
        "ollama": settings.evidence_vision_model,
        "openrouter": OPENROUTER_VISION_MODEL,
        "qwen_cloud": settings.evidence_vision_cloud_model,
    }[settings.evidence_vision_provider]


def infer(images: list[SanitizedImage], prompt: str, schema: dict, *, max_tokens: int = 2048) -> str:
    """Infer over locally redacted images. Callers validate the structured result."""
    if not images or len(images) > 10 or any(not isinstance(item, SanitizedImage) for item in images):
        raise ValueError("Expected 1 to 10 redacted images")
    for item in images:
        if not item.content.startswith(b"\x89PNG\r\n\x1a\n") or len(item.content) > 8 * 1024 * 1024:
            raise ValueError("VLM requires a PNG within the evidence size limit")
    prompt = f"{prompt}\nTrả về JSON theo schema sau: {dumps(schema, ensure_ascii=False)}"
    if settings.evidence_vision_provider == "ollama":
        with httpx.Client(timeout=httpx.Timeout(90, connect=3), trust_env=False, follow_redirects=False) as client:
            response = client.post(
                settings.evidence_vision_url + "/api/chat",
                json={
                    "model": model_id(),
                    "stream": False,
                    "think": False,
                    "format": schema,
                    "options": {"temperature": 0, "num_predict": max_tokens},
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [b64encode(item.content).decode("ascii") for item in images],
                        }
                    ],
                },
            )
            response.raise_for_status()
        body = response.json()
        if body.get("done") is not True or body.get("done_reason") != "stop":
            raise ValueError("VLM did not complete the response")
        return body["message"]["content"]
    if settings.evidence_vision_provider == "openrouter":
        key = settings.openrouter_api_key.get_secret_value().strip()
        url = "https://openrouter.ai/api/v1/chat/completions"
        model = OPENROUTER_VISION_MODEL
        routing = {"provider": {"only": ["parasail"], "allow_fallbacks": False, "require_parameters": True}}
    else:
        key = settings.dashscope_api_key.get_secret_value().strip()
        workspace = settings.dashscope_workspace_id
        host = f"{workspace}.ap-southeast-1.maas.aliyuncs.com" if workspace else "dashscope-intl.aliyuncs.com"
        url = f"https://{host}/compatible-mode/v1/chat/completions"
        model = settings.evidence_vision_cloud_model
        routing = {}
    if not key:
        raise VisionProviderNotConfigured()
    with httpx.Client(timeout=httpx.Timeout(90, connect=5), trust_env=False, follow_redirects=False) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                **routing,
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
