from pydantic import BaseModel


class RuleUpdateRequest(BaseModel):
    require_evidence: bool
    require_readable_ocr: bool
    require_shift: bool
    require_punch: bool
