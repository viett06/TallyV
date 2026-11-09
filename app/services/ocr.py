"""Read evidence using the explicitly selected OCR backend."""

from base64 import b64encode
from io import BytesIO
from typing import Annotated, Literal

import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.schema.ocr import OcrLine, OcrResponse
from app.services.evidence_cloud import CloudProviderNotConfigured, validate_cloud_image

VLMRUN_OCR_MODEL = "paddleocr/pp-ocrv6"
VLMRUN_OCR_URL = "https://gateway.vlm.run/openai/chat/completions"
NormalizedCoordinate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class GatewayOcrLine(BaseModel):
    model_config = ConfigDict(strict=True)
    bbox_xywh: tuple[NormalizedCoordinate, NormalizedCoordinate, NormalizedCoordinate, NormalizedCoordinate]
    text: str = Field(max_length=12000)
    score: NormalizedCoordinate


class GatewayOcrContent(BaseModel):
    object: Literal["doc.ocr.lines"]
    items: list[GatewayOcrLine] = Field(max_length=1000)


class GatewayOcrResult(BaseModel):
    model: Literal["paddleocr/pp-ocrv6"]
    method: Literal["ocr"]
    content: GatewayOcrContent


def read_vlmrun(content: bytes) -> OcrResponse:
    validate_cloud_image(content)
    token = settings.vlmrun_api_key.get_secret_value().strip()
    if not token:
        raise CloudProviderNotConfigured()
    image_url = "data:image/png;base64," + b64encode(content).decode("ascii")
    with httpx.Client(
        timeout=httpx.Timeout(settings.ocr_api_timeout, connect=3),
        trust_env=False,
        follow_redirects=False,
    ) as client:
        response = client.post(
            VLMRUN_OCR_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": VLMRUN_OCR_MODEL,
                "method": "ocr",
                "method_params": {"lang": settings.vlmrun_ocr_lang},
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_url}}]}],
            },
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        result = GatewayOcrResult.model_validate_json(message["content"])

    lines = []
    for item in result.content.items:
        x, y, width, height = item.bbox_xywh
        box = (x, y, min(1.0, x + width), min(1.0, y + height))
        lines.append(OcrLine(text=item.text, score=item.score, box=box))
    return OcrResponse(model=result.model, lines=lines)


def read_text(content: bytes, *, regions: list | None = None) -> str:
    if settings.ocr_backend == "vlmrun":
        result = read_vlmrun(content)
    elif settings.ocr_backend in {"http", "remote"}:
        remote = settings.ocr_backend == "remote"
        base_url = settings.ocr_api_url
        headers = {}
        if remote:
            validate_cloud_image(content)
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
    else:
        return read_tesseract(content, regions)
    if regions is not None:
        regions.extend(line.model_dump(mode="json") for line in result.lines if line.box)
    return "\n".join(line.text for line in result.lines)


def read_tesseract(content: bytes, regions: list | None) -> str:
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
