from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["FORGOT_CHECK", "DEVICE_ERROR", "LEAVE_NOT_RECORDED", "UNKNOWN"]
    reason: str = Field(min_length=1, max_length=600)
    extracted: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list, max_length=20)
    conflicts: list[str] = Field(default_factory=list, max_length=20)
