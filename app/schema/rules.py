from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

RuleDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
RuleLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
RuleKeyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
RuleCategory = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,39}$")]


class RuleUpdateRequest(BaseModel):
    require_evidence: bool
    require_readable_ocr: bool
    require_shift: bool
    require_punch: bool
    description: RuleDescription = Field(default="")
    label: RuleLabel | None = None
    keywords: list[RuleKeyword] = Field(default_factory=list, max_length=20)


class RuleCreateRequest(RuleUpdateRequest):
    label: RuleLabel
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
