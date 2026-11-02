# syntax=docker/dockerfile:1
# Build from the repository root:
# docker build -f ocr_service/Dockerfile -t tallyv-ocr:local .
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    OCR_SERVICE_MODELS_DIR=/models \
    OCR_SERVICE_CPU_THREADS=4

WORKDIR /app

# Shared libraries used by PaddlePaddle and the OpenCV dependency.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates libgl1 libglib2.0-0 libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# Keep model/runtime dependencies separate from the TallyV application image.
# Official CPU index provides Python 3.11 wheels for Linux ARM64 and AMD64.
COPY requirements-ocr.txt ./requirements-ocr.txt
RUN python -m pip install 'paddlepaddle==3.3.0' \
        --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/ \
    && python -m pip install -r requirements-ocr.txt \
    && python -m pip check \
    && python -c "import paddle; from paddleocr import PaddleOCR; print(paddle.__version__)"

COPY ocr_service/__init__.py ocr_service/app.py ./ocr_service/

RUN useradd --uid 10001 --create-home ocr \
    && mkdir -p /models /home/ocr/.cache /home/ocr/.paddlex \
    && chown -R ocr:ocr /models /home/ocr

ENV HOME=/home/ocr \
    PADDLE_PDX_CACHE_HOME=/home/ocr/.paddlex

USER ocr
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3).close()"]

CMD ["python", "-m", "uvicorn", "ocr_service.app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "--no-access-log"]
