"""Read evidence using the explicitly selected local OCR backend."""

from io import BytesIO

import httpx
from PIL import Image

from app.core.config import settings
from app.schema.ocr import OcrResponse


def read_text(content: bytes) -> str:
    if settings.ocr_backend == "http":
        # Ignore proxy environment variables and never follow an upstream redirect.
        with httpx.Client(
            timeout=httpx.Timeout(settings.ocr_api_timeout, connect=3),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = client.post(
                settings.ocr_api_url + "/ocr",
                files={"file": ("evidence.png", content, "image/png")},
            )
            response.raise_for_status()
            result = OcrResponse.model_validate(response.json())
        return "\n".join(line.text for line in result.lines)

    import pytesseract

    with Image.open(BytesIO(content)) as image:
        return pytesseract.image_to_string(image, lang="eng", config="--psm 6", timeout=12)
