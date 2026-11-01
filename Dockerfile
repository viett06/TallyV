FROM node:22-alpine AS frontend
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-vie fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini main.py hr_mock_app.py ./
COPY --from=frontend /web/dist ./frontend/dist
RUN useradd --uid 10001 --create-home demo && mkdir -p /app/data && chown -R demo:demo /app/data
USER demo
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
