"""Wire contract for the separately hosted OCR service."""

from pydantic import BaseModel, ConfigDict, Field


class OcrLine(BaseModel):
    model_config = ConfigDict(strict=True)
    text: str = Field(max_length=12000)
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class OcrResponse(BaseModel):
    lines: list[OcrLine] = Field(max_length=1000)
