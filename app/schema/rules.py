from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

RuleDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
RuleLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
RuleCategory = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,39}$")]


class RuleUpdateRequest(BaseModel):
    require_evidence: bool
    require_shift: bool
    require_punch: bool
    description: RuleDescription = Field(default="")
    label: RuleLabel | None = None


class RuleCreateRequest(RuleUpdateRequest):
    label: RuleLabel
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
