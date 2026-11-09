"""Bounded protocol to the internal Python execution host."""

import json
import ssl

import httpx
from pydantic import ValidationError

from app.assistant.config import settings
from app.assistant.errors import AppError, InputError
from app.assistant.schema.sandbox import MAX_INPUT, MAX_OUTPUT, ExecutionRequest, ExecutionResult


def execute(request: ExecutionRequest) -> ExecutionResult:
    token = settings.sandbox_token.get_secret_value()
    if not settings.sandbox_url or not token:
        raise AppError(503, "Chưa cấu hình runner sandbox nội bộ cho Assistant.")
    body = json.dumps(request.model_dump(), ensure_ascii=False, allow_nan=False).encode()
    if len(body) > MAX_INPUT:
        raise InputError("Dữ liệu cho sandbox vượt 32 MB. Hãy chọn ít sheet hoặc ít dòng hơn.")
    try:
        tls = ssl.create_default_context(cafile=settings.sandbox_ca_file) if settings.sandbox_ca_file else True
        with httpx.Client(timeout=request.timeout + 20, trust_env=False, follow_redirects=False, verify=tls) as client:
            with client.stream(
                "POST",
                settings.sandbox_url + "/execute",
                content=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_OUTPUT + 1024:
                        return ExecutionResult(error="OUTPUT_LIMIT")
        result = ExecutionResult.model_validate_json(content)
        if (result.result is None) == (result.error is None):
            return ExecutionResult(error="INVALID_OUTPUT")
        return result
    except (httpx.HTTPError, OSError, ValidationError) as error:
        raise AppError(503, "Không thể chạy script trong sandbox nội bộ đã cấu hình.") from error
