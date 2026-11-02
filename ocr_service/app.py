"""Run with: python -m uvicorn ocr_service.app:app --host 127.0.0.1 --port 8001 --workers 1."""

import logging
import os
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)
MODEL_NAMES = ("PP-OCRv6_small_det", "PP-OCRv6_small_rec")


class ServiceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models_dir: Path = Path(__file__).resolve().parents[2] / "tallyv-ocr" / "models"
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


class Line(BaseModel):
    model_config = ConfigDict(strict=True)
    text: str = Field(max_length=12000)
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class OcrOutput(BaseModel):
    model: str = "PP-OCRv6_small"
    lines: list[Line] = Field(max_length=1000)


class LocalOcr:
    def __init__(self, config: ServiceSettings):
        root = config.models_dir.expanduser().resolve()
        for name in MODEL_NAMES:
            for filename in ("inference.json", "inference.pdiparams", "inference.yml"):
                if not (root / name / filename).is_file():
                    raise RuntimeError(f"Missing local model file: {root / name / filename}")

        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        # Import only during startup, after local model paths have been checked.
        from paddleocr import PaddleOCR

        self.model = PaddleOCR(
            device="cpu",
            engine="paddle_static",
            enable_hpi=False,
            enable_mkldnn=False,
            cpu_threads=config.cpu_threads,
            text_detection_model_name=MODEL_NAMES[0],
            text_detection_model_dir=str(root / MODEL_NAMES[0]),
            text_recognition_model_name=MODEL_NAMES[1],
            text_recognition_model_dir=str(root / MODEL_NAMES[1]),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        self.lock = Lock()

    def predict(self, path: Path) -> OcrOutput:
        lines = []
        with self.lock:
            for result in self.model.predict(str(path)):
                texts, scores = result["rec_texts"], result["rec_scores"]
                for text, score in zip(texts, scores, strict=True):
                    lines.append(Line(text=text, score=float(score)))
        return OcrOutput(lines=lines)

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
        return {"status": "ready", "model": "PP-OCRv6_small"}

    @service.post("/ocr", response_model=OcrOutput)
    def read_image(file: UploadFile = File(...)):
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
