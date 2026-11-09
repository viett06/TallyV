"""Shared request limits and response shapes for the Assistant sandbox."""

from typing import Literal

from pydantic import Field

from app.assistant.schema.planning import StrictModel

MAX_INPUT = 32 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024


class ExecutionRequest(StrictModel):
    code: str = Field(min_length=1, max_length=36_000)
    sources: dict[str, dict]
    steps: list[dict] = Field(max_length=20)
    outputs: list[str] = Field(min_length=1, max_length=30)
    timeout: int = Field(ge=5, le=120)


class ExecutionResult(StrictModel):
    result: dict | None = None
    error: Literal["SCRIPT_ERROR", "TIME_LIMIT", "OUTPUT_LIMIT", "INVALID_OUTPUT"] | None = None
