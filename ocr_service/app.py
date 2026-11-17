"""Run with: python -m uvicorn ocr_service.app:app --host 127.0.0.1 --port 8001 --workers 1."""

import logging
import os
from contextlib import asynccontextmanager
from hmac import compare_digest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Annotated

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, SecretStr

logger = logging.getLogger(__name__)
MODEL_NAME = "PP-OCRv6_small_det"


class ServiceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models_dir: Path = Path(__file__).resolve().parent / "models"
    api_token: SecretStr = SecretStr("")
    cpu_threads: int = Field(default=4, ge=1, le=64)
    max_upload_bytes: int = Field(default=8 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=16_000_000, gt=0)

    @classmethod
    def from_env(cls):
        return cls.model_validate(
            {
                name: os.environ["OCR_SERVICE_" + name.upper()]
                for name in cls.model_fields
                if "OCR_SERVICE_" + name.upper() in os.environ
            }
        )


class OcrOutput(BaseModel):
    model: str = MODEL_NAME
    regions: list[tuple[float, float, float, float]] = Field(max_length=1000)


class LocalOcr:
    def __init__(self, config: ServiceSettings):
        model_dir = config.models_dir.expanduser().resolve() / MODEL_NAME
        for filename in ("inference.json", "inference.pdiparams", "inference.yml"):
            if not (model_dir / filename).is_file():
                raise RuntimeError(f"Missing local model file: {model_dir / filename}")

        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import TextDetection

        self.model = TextDetection(
            model_name=MODEL_NAME,
            model_dir=str(model_dir),
            device="cpu",
            engine="paddle_static",
            enable_hpi=False,
            enable_mkldnn=False,
            cpu_threads=config.cpu_threads,
        )
        self.lock = Lock()

    def predict(self, path: Path) -> OcrOutput:
        regions = []
        with Image.open(path) as image:
            width, height = image.size
        with self.lock:
            for result in self.model.predict(str(path)):
                for polygon in result["dt_polys"]:
                    x_coords, y_coords = zip(*polygon, strict=True)
                    regions.append(
                        (
                            max(0, int(min(x_coords))) / width,
                            max(0, int(min(y_coords))) / height,
                            min(width, int(max(x_coords)) + 1) / width,
                            min(height, int(max(y_coords)) + 1) / height,
                        )
                    )
        return OcrOutput(regions=regions)

    def close(self):
        self.model.close()


def create_app(config: ServiceSettings | None = None, runtime_factory=LocalOcr) -> FastAPI:
    config = config or ServiceSettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ocr = runtime_factory(config)
        try:
            yield
        finally:
            app.state.ocr.close()

    service = FastAPI(title="TallyV local OCR", version="1.0.0", lifespan=lifespan)

    @service.get("/health")
    def health():
        return {"status": "ready", "model": MODEL_NAME}

    @service.post("/ocr", response_model=OcrOutput)
    def read_image(file: UploadFile = File(...), authorization: Annotated[str | None, Header()] = None):
        token = config.api_token.get_secret_value()
        if token and not compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
            raise HTTPException(401, "Invalid OCR credentials", headers={"WWW-Authenticate": "Bearer"})
        content = file.file.read(config.max_upload_bytes + 1)
        if len(content) > config.max_upload_bytes:
            raise HTTPException(413, "Image exceeds upload size limit")
        with TemporaryDirectory(prefix="tallyv-ocr-") as folder:
            path = Path(folder) / "input.png"
            try:
                with Image.open(BytesIO(content)) as image:
                    if image.format not in {"PNG", "JPEG"}:
                        raise HTTPException(415, "Only PNG and JPEG images are supported")
                    if image.width * image.height > config.max_image_pixels:
                        raise HTTPException(413, "Image exceeds pixel limit")
                    ImageOps.exif_transpose(image).convert("RGB").save(path)
            except Image.DecompressionBombError:
                raise HTTPException(413, "Image exceeds pixel limit") from None
            except (UnidentifiedImageError, OSError, ValueError):
                raise HTTPException(400, "Invalid image") from None

            try:
                return service.state.ocr.predict(path)
            except Exception as error:
                # Never log image bytes, recognized text, or arbitrary model errors.
                logger.warning("OCR inference failed: %s", type(error).__name__)
                raise HTTPException(503, "OCR inference unavailable") from None

    return service


app = create_app()
