from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Preserve the existing ISO timestamp representation, including +00:00.
IsoDateTime = Annotated[datetime, PlainSerializer(lambda value: value.isoformat(), return_type=str)]


class View(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OperationResult(BaseModel):
    ok: bool


class JobQueued(BaseModel):
    job_id: int


class HealthView(BaseModel):
    status: str
    data: str
