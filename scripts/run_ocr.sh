#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ocr_python="${OCR_PYTHON:-$repo_dir/../tallyv-ocr/venv/bin/python}"

if [[ ! -x "$ocr_python" ]]; then
    echo "OCR Python not found. Set OCR_PYTHON to the Python in your OCR virtual environment." >&2
    exit 1
fi

cd -- "$repo_dir"
exec "$ocr_python" -m uvicorn ocr_service.app:app \
    --host 127.0.0.1 --port "${OCR_SERVICE_PORT:-8001}" --workers 1 --no-access-log
