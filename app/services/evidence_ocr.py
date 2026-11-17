"""Read text boxes from the internal OCR service without retaining recognized text."""

from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.services.evidence_masking import TextBox


class TextRegions(BaseModel):
    model_config = ConfigDict(strict=True)
    model: Literal["PP-OCRv6_small_det"]
    regions: list[TextBox] = Field(max_length=1000)


def detect_text(content: bytes) -> list[TextBox]:
    token = settings.ocr_service_api_token.get_secret_value()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(timeout=httpx.Timeout(60, connect=3), trust_env=False, follow_redirects=False) as client:
        response = client.post(
            settings.evidence_ocr_url + "/ocr",
            files={"file": ("masked.png", content, "image/png")},
            headers=headers,
        )
        response.raise_for_status()
    return TextRegions.model_validate_json(response.content).regions
