"""Read evidence using the explicitly selected OCR backend."""

from io import BytesIO

import httpx
from PIL import Image

from app.core.config import settings
from app.schema.ocr import OcrLine, OcrResponse
from app.services.evidence_cloud import CloudProviderNotConfigured, require_approved_image


def read_text(content: bytes, *, regions: list | None = None) -> str:
    if settings.ocr_backend in {"http", "remote"}:
        remote = settings.ocr_backend == "remote"
        base_url = settings.ocr_api_url
        headers = {}
        if remote:
            require_approved_image(content)
            base_url = settings.ocr_remote_url
            token = settings.ocr_remote_api_token.get_secret_value().strip()
            if not base_url or not token:
                raise CloudProviderNotConfigured()
            headers["Authorization"] = f"Bearer {token}"
        # Ignore proxy environment variables and never follow an upstream redirect.
        with httpx.Client(
            timeout=httpx.Timeout(settings.ocr_api_timeout, connect=3),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = client.post(
                base_url + "/ocr",
                files={"file": ("evidence.png", content, "image/png")},
                headers=headers,
            )
            response.raise_for_status()
            result = OcrResponse.model_validate_json(response.content)
        if remote and result.model != settings.ocr_remote_model:
            raise ValueError("Remote OCR returned a different model")
        if regions is not None:
            regions.extend(line.model_dump(mode="json") for line in result.lines if line.box)
        return "\n".join(line.text for line in result.lines)

    import pytesseract

    with Image.open(BytesIO(content)) as image:
        words = pytesseract.image_to_data(
            image, lang="eng+vie", config="--psm 6", timeout=12, output_type=pytesseract.Output.DICT
        )
        width, height = image.size
    groups = {}
    for i, value in enumerate(words["text"]):
        if not value.strip():
            continue
        key = tuple(words[field][i] for field in ("block_num", "par_num", "line_num"))
        groups.setdefault(key, []).append(i)
    lines = []
    for indices in groups.values():
        text = " ".join(words["text"][i] for i in indices)
        lines.append(text)
        if regions is not None:
            x1 = min(words["left"][i] for i in indices) / width
            y1 = min(words["top"][i] for i in indices) / height
            x2 = max(words["left"][i] + words["width"][i] for i in indices) / width
            y2 = max(words["top"][i] + words["height"][i] for i in indices) / height
            score = sum(float(words["conf"][i]) for i in indices) / len(indices) / 100
            regions.append(
                OcrLine(text=text, score=max(0.0, min(1.0, score)), box=(x1, y1, x2, y2)).model_dump(mode="json")
            )
    return "\n".join(lines)
