import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True)
    database_url: str
    secret_key: str
    demo_password: str
    demo_username: str = "hr.demo"
    storage_dir: Path = ROOT / "data"
    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = "tallyv-files"
    s3_prefix: str = "tallyv/"
    s3_access_key_id: SecretStr = SecretStr("")
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_addressing_style: Literal["auto", "path", "virtual"] = "auto"
    mailpit_url: str = "http://127.0.0.1:8025"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    processing_mode: str = "GEMINI"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    gemini_provider: Literal["google", "openrouter"] = "google"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = Field(default="gemini-3.8-flash", pattern=r"^gemini-[a-z0-9.-]{1,80}$")
    jev_enabled: bool = False
    jev_provider: Literal["typesafe", "openrouter"] = "typesafe"
    jev_api_key: SecretStr = SecretStr("")
    jev_model: str = Field(default="jev-1.14.0", pattern=r"^jev-[a-z0-9.-]{1,80}$")
    jev_threshold: float = Field(default=0.85, gt=0.5, lt=1, allow_inf_nan=False)
    ocr_enabled: bool = False
    ocr_backend: Literal["tesseract", "http", "remote", "vlmrun"] = "tesseract"
    ocr_api_url: str = "http://127.0.0.1:8001"
    ocr_api_timeout: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)
    ocr_remote_url: str = ""
    ocr_remote_api_token: SecretStr = SecretStr("")
    ocr_remote_model: Literal["PP-OCRv6_small", "PP-OCRv6_medium"] = "PP-OCRv6_medium"
    vlmrun_api_key: SecretStr = SecretStr("")
    vlmrun_ocr_lang: str = Field(default="vi", pattern=r"^[a-z_]{2,20}$")
    evidence_history_enabled: bool = False
    evidence_history_model_path: Path | None = None
    evidence_vision_enabled: bool = False
    evidence_vision_provider: Literal["ollama", "qwen_cloud", "openrouter"] = "ollama"
    evidence_vision_url: str = "http://127.0.0.1:11434"
    evidence_vision_model: Literal[
        "qwen3-vl:2b", "qwen3-vl:4b", "qwen3-vl:2b-instruct", "qwen3-vl:4b-instruct", "qwen3-vl:8b-instruct"
    ] = "qwen3-vl:2b-instruct"
    evidence_vision_cloud_model: Literal["qwen3-vl-8b-instruct", "qwen3-vl-235b-a22b-instruct"] = "qwen3-vl-8b-instruct"
    dashscope_api_key: SecretStr = SecretStr("")
    dashscope_workspace_id: str = Field(default="", pattern=r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)?$")
    openrouter_api_key: SecretStr = SecretStr("")
    sync_interval: int = 30
    allowed_origins: str = "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173"
    cookie_secure: bool = False
    mail_provider: str = "outlook"
    outlook_transport: Literal["microsoft", "composio"] = "microsoft"
    composio_api_key: SecretStr = SecretStr("")
    composio_auth_config_id: str = ""
    composio_poll_interval: int = 0
    outlook_tenant_id: str = "common"
    outlook_client_id: str = ""
    outlook_client_secret: SecretStr = SecretStr("")
    outlook_redirect_uri: str = "http://localhost:8000/api/outlook/callback"
    outlook_sync_days: int = 90
    outlook_test_mode: bool = True
    hr_mock_url: str = "http://127.0.0.1:8010"
    hr_mock_api_key: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def valid_storage(self):
        if bool(self.s3_access_key_id.get_secret_value()) != bool(self.s3_secret_access_key.get_secret_value()):
            raise ValueError("Set both S3 credentials, or leave both blank to use the AWS credential chain")
        if not self.s3_bucket or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in self.s3_bucket):
            raise ValueError("Invalid S3 bucket name")
        if not self.s3_prefix.endswith("/") or any(c in self.s3_prefix for c in ('"', "*", "\\", "\n")):
            raise ValueError("S3_PREFIX must end with / and contain no wildcard or escape characters")
        if self.s3_endpoint_url:
            parsed = urlparse(self.s3_endpoint_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("Use an HTTP(S) S3 endpoint without credentials or a path")
            if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "minio"}:
                raise ValueError("S3 endpoints outside local MinIO must use HTTPS")
        return self

    @model_validator(mode="after")
    def synthetic_composio_only(self):
        if self.mail_provider == "outlook" and self.outlook_transport == "composio" and not self.outlook_test_mode:
            raise ValueError("Composio is restricted to synthetic MVP data; OUTLOOK_TEST_MODE must remain true")
        return self

    @field_validator("composio_poll_interval")
    @classmethod
    def valid_composio_poll_interval(cls, value):
        if value != 0 and value < 60:
            raise ValueError("COMPOSIO_POLL_INTERVAL must be 0 (manual sync) or at least 60 seconds")
        return value

    @field_validator("mail_provider")
    @classmethod
    def valid_mail_provider(cls, value):
        if value not in {"mailpit", "outlook"}:
            raise ValueError("MAIL_PROVIDER must be mailpit or outlook")
        return value

    @field_validator("outlook_tenant_id")
    @classmethod
    def valid_microsoft_tenant(cls, value):
        value = value.strip().lower()
        if value == "common":
            return value
        return str(UUID(value)) if value else value

    @field_validator("outlook_client_id")
    @classmethod
    def valid_microsoft_id(cls, value):
        return str(UUID(value.strip())) if value.strip() else ""

    @field_validator("outlook_redirect_uri")
    @classmethod
    def valid_redirect(cls, value):
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path != "/api/outlook/callback"
            or (parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"})
        ):
            raise ValueError("Use an HTTPS callback, or localhost HTTP for development")
        return value

    @field_validator("outlook_sync_days")
    @classmethod
    def valid_sync_days(cls, value):
        if not 1 <= value <= 365:
            raise ValueError("OUTLOOK_SYNC_DAYS must be between 1 and 365")
        return value

    @field_validator("secret_key")
    @classmethod
    def valid_secret(cls, value):
        if len(value) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        return value

    @field_validator("demo_password")
    @classmethod
    def valid_password(cls, value):
        if len(value) < 10:
            raise ValueError("DEMO_PASSWORD must contain at least 10 characters")
        return value

    @field_validator("processing_mode")
    @classmethod
    def valid_mode(cls, value):
        if value not in {"RULE_BASED", "LOCAL_LLM", "GEMINI"}:
            raise ValueError("Unknown processing mode")
        return value

    @model_validator(mode="after")
    def gemini_credentials(self):
        if self.processing_mode == "GEMINI":
            key = self.openrouter_api_key if self.gemini_provider == "openrouter" else self.gemini_api_key
            if not key.get_secret_value().strip():
                name = "OPENROUTER_API_KEY" if self.gemini_provider == "openrouter" else "GEMINI_API_KEY"
                raise ValueError(f"{name} is required when PROCESSING_MODE=GEMINI")
        if self.jev_enabled:
            if self.processing_mode != "GEMINI":
                raise ValueError("JEV_ENABLED requires PROCESSING_MODE=GEMINI")
            key = self.openrouter_api_key if self.jev_provider == "openrouter" else self.jev_api_key
            if not key.get_secret_value().strip():
                name = "OPENROUTER_API_KEY" if self.jev_provider == "openrouter" else "JEV_API_KEY"
                raise ValueError(f"{name} is required when JEV_ENABLED=true")
        return self

    @field_validator("ocr_remote_url")
    @classmethod
    def remote_ocr_https(cls, value):
        value = value.strip().rstrip("/")
        if value:
            parsed = urlparse(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("OCR_REMOTE_URL must be an HTTPS base URL without embedded credentials")
        return value

    @field_validator("mailpit_url", "ollama_url", "hr_mock_url", "ocr_api_url", "evidence_vision_url")
    @classmethod
    def internal_url(cls, value):
        parsed = urlparse(value)
        host = parsed.hostname or ""
        allowed = host in {"localhost", "mailpit", "ollama", "hr-mock", "host.docker.internal"}
        try:
            address = ipaddress.ip_address(host)
            allowed = address.is_loopback or address.is_private
        except ValueError:
            pass
        if (
            parsed.scheme != "http"
            or not allowed
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Only explicit internal HTTP endpoints are allowed")
        return value.rstrip("/")


settings = Settings()
