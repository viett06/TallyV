"""Structured output for visual attendance assessment."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schema.rules import RuleCategory


class ImageAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_ref: int = Field(ge=1)
    relation: Literal["SUPPORTS", "CONTRADICTS", "INSUFFICIENT"]
    observation: str = Field(min_length=1, max_length=400)
    limitations: str = Field(min_length=1, max_length=400)


class VisualAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    category: RuleCategory
    reason: str = Field(min_length=1, max_length=600)
    evidence_assessments: list[ImageAssessment]
