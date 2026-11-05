from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filter(StrictModel):
    column: str
    operator: Literal["eq", "contains", "date_month", "ne"]
    value: str


class Rewrite(StrictModel):
    paragraph_id: str
    text: str


class Correction(StrictModel):
    row: int = Field(ge=1, le=200)
    column: str
    value: str


class Plan(StrictModel):
    mapping: dict[str, str] = Field(default_factory=dict)
    constants: dict[str, str] = Field(default_factory=dict)
    rewrites: list[Rewrite] = Field(default_factory=list, max_length=100)
    filters: list[Filter] = Field(default_factory=list, max_length=10)
    corrections: list[Correction] = Field(default_factory=list, max_length=100)
    question: str | None = None
    skip_incomplete: bool = False
    email_requested: bool = False
    email_subject: str = ""
    email_body: str = ""


class ExtractedData(StrictModel):
    records: list[dict[str, str]] = Field(max_length=200)
    question: str | None = None
