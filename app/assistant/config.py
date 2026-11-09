from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import ROOT, Settings


class AssistantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="ASSISTANT_", extra="ignore")
    processing_mode: Literal["LOCAL_LLM", "RULE_BASED", "HYBRID"] = "LOCAL_LLM"
    ollama_url: str = "http://127.0.0.1:11435"
    ollama_model: str = "llama3.2:latest"
    hybrid_ollama_model: str = "qwen3.5:4b-q4_K_M"
    openrouter_model: str = Field(default="openai/gpt-5.4-mini", pattern=r"^openai/gpt-[a-zA-Z0-9.-]+$")
    sandbox_url: str = ""
    sandbox_token: SecretStr = SecretStr("")
    sandbox_ca_file: str = ""
    sandbox_timeout: int = Field(default=90, ge=5, le=120)
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

    @field_validator("sandbox_url")
    @classmethod
    def sandbox_endpoint(cls, value):
        if not value:
            return value
        url = urlsplit(value)
        loopback = url.hostname in {"127.0.0.1", "::1", "localhost"}
        if (
            not url.hostname
            or (url.scheme != "https" and not (url.scheme == "http" and loopback))
            or url.username
            or url.password
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError("Sandbox needs an HTTPS origin or a loopback HTTP origin")
        return value.rstrip("/")


settings = AssistantSettings()
