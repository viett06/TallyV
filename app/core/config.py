import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str
    secret_key: str
    demo_password: str
    demo_username: str = "hr.demo"
    storage_dir: Path = ROOT / "data"
    mailpit_url: str = "http://127.0.0.1:8025"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    processing_mode: str = "RULE_BASED"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ocr_enabled: bool = False
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
        if value not in {"RULE_BASED", "LOCAL_LLM"}:
            raise ValueError("Unknown processing mode")
        return value

    @field_validator("mailpit_url", "ollama_url", "hr_mock_url")
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
