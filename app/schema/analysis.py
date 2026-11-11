from pydantic import BaseModel, ConfigDict, Field

from app.schema.rules import RuleCategory


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: RuleCategory
    reason: str = Field(min_length=1, max_length=600)
    extracted: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list, max_length=20)
    conflicts: list[str] = Field(default_factory=list, max_length=20)
