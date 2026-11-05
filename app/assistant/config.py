from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import ROOT, Settings


class AssistantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="ASSISTANT_", extra="ignore")
    processing_mode: Literal["LOCAL_LLM", "RULE_BASED"] = "LOCAL_LLM"
    ollama_url: str = "http://127.0.0.1:11435"
    ollama_model: str = "llama3.2:latest"
    model_timeout: float = Field(default=120, ge=10, le=240, allow_inf_nan=False)
    max_upload_bytes: int = 15 * 1024 * 1024
    max_rows: int = 200
    max_data_rows: int = Field(default=10000, ge=1, le=50000)
    max_steps: int = Field(default=20, ge=1, le=40)
    max_model_calls: int = Field(default=12, ge=1, le=30)
    max_task_seconds: int = Field(default=900, ge=30, le=3600)

    @field_validator("ollama_url")
    @classmethod
    def internal_model(cls, value):
        return Settings.internal_url(value)


settings = AssistantSettings()
