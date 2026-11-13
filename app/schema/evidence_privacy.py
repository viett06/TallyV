"""Application batch inputs; independent of any background transport or queue."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PreprocessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    version_id: int = Field(gt=0)


class SafeArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_id: int = Field(gt=0)
    artifact: str = Field(pattern=r"^[0-9a-f]{32}\.png$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssessmentRequest(PreprocessRequest):
    privacy_request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    privacy_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    images: list[SafeArtifact]


class RequestedVersion(PreprocessRequest):
    privacy_request_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class ImageBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    requests: list[RequestedVersion] = Field(min_length=1, max_length=10000)
    analyze: bool = False
