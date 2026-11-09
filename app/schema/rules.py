from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

RuleDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class RuleUpdateRequest(BaseModel):
    require_evidence: bool
    require_readable_ocr: bool
    require_shift: bool
    require_punch: bool
    description: RuleDescription = Field(default="")
