"""Read evidence using the explicitly selected local OCR backend."""

from pathlib import Path

import httpx
from PIL import Image

from app.core.config import settings
from app.schema.ocr import OcrResponse


def read_text(path: Path) -> str:
    if settings.ocr_backend == "http":
        content_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        # Ignore proxy environment variables and never follow an upstream redirect.
        with (
            path.open("rb") as source,
            httpx.Client(
                timeout=httpx.Timeout(settings.ocr_api_timeout, connect=3),
                trust_env=False,
                follow_redirects=False,
            ) as client,
        ):
            response = client.post(
                settings.ocr_api_url + "/ocr",
                files={"file": ("evidence" + path.suffix.lower(), source, content_type)},
            )
            response.raise_for_status()
            result = OcrResponse.model_validate(response.json())
        return "\n".join(line.text for line in result.lines)

    import pytesseract

    with Image.open(path) as image:
        return pytesseract.image_to_string(image, lang="eng", config="--psm 6", timeout=12)
