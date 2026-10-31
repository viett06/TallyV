import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schema.common import IsoDateTime


class OutlookStatus(BaseModel):
    provider: str
    transport: str
    connected_transport: str | None = None
    configured: bool
    status: str
    mailbox: str
    connected_at: IsoDateTime | None = None
    last_synced_at: IsoDateTime | None = None
    sync_status: str | None = None
    sync_error: str | None = None
    sync_summary: dict[str, int] = Field(default_factory=dict)
    sync_days: int
    redirect_uri: str
    test_mode: bool


class OutlookAuthorization(BaseModel):
    authorization_url: str


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    senders: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("name", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("senders")
    @classmethod
    def valid_senders(cls, values):
        normalized = sorted({address.strip().lower() for address in values})
        if any(len(address) > 200 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", address) for address in normalized):
            raise ValueError("Each sender must be an email address")
        return normalized


class EmployeeImportResult(BaseModel):
    imported: int
