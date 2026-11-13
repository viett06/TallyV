"""Exact-layout masking. Unknown, ambiguous or unreadable inputs never pass."""

from base64 import b64decode
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
from typing import Literal

import cv2
import numpy as np
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "fixed-layout-v1"
MAX_BYTES = 8 * 1024 * 1024


class Rect(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)

    def slices(self):
        return slice(self.y, self.y + self.h), slice(self.x, self.x + self.w)


class Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    rect: Rect
    rgb_base64: str = Field(min_length=1, max_length=262144)
    max_mean_error: float = Field(default=3, ge=0, le=10, allow_inf_nan=False)
    max_changed_fraction: float = Field(default=0.01, ge=0, le=0.05, allow_inf_nan=False)

    def pixels(self):
        raw = b64decode(self.rgb_base64, validate=True)
        if len(raw) != self.rect.w * self.rect.h * 3:
            raise ValueError("Anchor dimensions do not match RGB bytes")
        return np.frombuffer(raw, dtype=np.uint8).reshape(self.rect.h, self.rect.w, 3)


class LayoutProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    enabled: bool = False
    kind: Literal["FACEID", "DEVICE_ERROR"]
    width: int = Field(gt=0, le=8000)
    height: int = Field(gt=0, le=8000)
    anchors: list[Anchor] = Field(min_length=2, max_length=8)
    keep_regions: list[Rect] = Field(min_length=1, max_length=16)
    pii_regions: list[Rect] = Field(min_length=1, max_length=16)
    face_region: Rect | None = None

    @model_validator(mode="after")
    def valid_geometry(self):
        if self.width * self.height > 16_000_000:
            raise ValueError("Profile exceeds pixel limit")
        if self.kind == "FACEID" and self.face_region is None:
            raise ValueError("FACEID requires a conservative fixed face region")
        rectangles = [*self.keep_regions, *self.pii_regions, *(a.rect for a in self.anchors)]
        if self.face_region:
            rectangles.append(self.face_region)
        for rect in rectangles:
            if rect.x + rect.w > self.width or rect.y + rect.h > self.height:
                raise ValueError("Rectangle outside profile dimensions")
        for anchor in self.anchors:
            patch = anchor.pixels()
            if anchor.rect.w * anchor.rect.h < 64 or float(patch.std(axis=(0, 1)).max()) < 5:
                raise ValueError("Anchors must contain distinctive static UI detail")
            for sensitive in [*self.pii_regions, *([self.face_region] if self.face_region else [])]:
                a = anchor.rect
                if (
                    a.x < sensitive.x + sensitive.w
                    and sensitive.x < a.x + a.w
                    and a.y < sensitive.y + sensitive.h
                    and sensitive.y < a.y + a.h
                ):
                    raise ValueError("Static anchors must not contain a PII or face region")
        for i, first in enumerate(self.anchors):
            for second in self.anchors[i + 1 :]:
                a, b = first.rect, second.rect
                if a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h:
                    raise ValueError("Static anchors must be distinct and non-overlapping")
        return self


class ProfileSet(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    profiles: list[LayoutProfile] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({p.id for p in self.profiles}) != len(self.profiles):
            raise ValueError("Duplicate profile IDs")
        return self

    @property
    def revision(self):
        return sha256((VERSION + self.model_dump_json()).encode()).hexdigest()


@dataclass(frozen=True)
class SanitizedImage:
    content: bytes = field(repr=False)
    sha256: str
    profile_id: str
    kind: str


@dataclass(frozen=True)
class Outcome:
    status: Literal["READY", "MANUAL_REVIEW"]
    reason: str
    metrics: dict = field(default_factory=dict)
    image: SanitizedImage | None = None


def decode(content: bytes) -> np.ndarray:
    if not content or len(content) > MAX_BYTES:
        raise ValueError("Image exceeds byte limit")
    with Image.open(BytesIO(content)) as source:
        if source.width * source.height > 16_000_000 or getattr(source, "n_frames", 1) != 1:
            raise ValueError("Unsupported evidence dimensions or animation")
        source.load()  # Do not accept truncated/lazy decoded inputs.
        oriented = ImageOps.exif_transpose(source).convert("RGBA")
        background = Image.new("RGBA", oriented.size, "white")
        background.alpha_composite(oriented)
        return np.array(background.convert("RGB"))


def _matches(rgb, profile):
    if rgb.shape[:2] != (profile.height, profile.width):
        return False
    for anchor in profile.anchors:
        actual = rgb[anchor.rect.slices()].astype(np.int16)
        expected = anchor.pixels().astype(np.int16)
        difference = np.abs(actual - expected)
        if float(difference.mean()) > anchor.max_mean_error:
            return False
        if float((difference.max(axis=2) > 20).mean()) > anchor.max_changed_fraction:
            return False
    return True


def process(content: bytes, profiles: ProfileSet) -> Outcome:
    """No learned classifier, OCR, face detector, network, or source-file mutation."""
    try:
        rgb = decode(content)
    except (ValueError, OSError, SyntaxError, Image.DecompressionBombError):
        return Outcome("MANUAL_REVIEW", "UNREADABLE_IMAGE")
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    metrics = {
        "mean_brightness": round(float(gray.mean()), 2),
        "dark_fraction": round(float((gray < 15).mean()), 4),
        "bright_fraction": round(float((gray > 240).mean()), 4),
        "laplacian_variance": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2),
    }
    matches = [profile for profile in profiles.profiles if profile.enabled and _matches(rgb, profile)]
    if len(matches) != 1:
        return Outcome("MANUAL_REVIEW", "UNKNOWN_LAYOUT" if not matches else "AMBIGUOUS_LAYOUT", metrics)
    profile = matches[0]
    # Start with black pixels; only explicitly permitted regions can survive.
    output = np.zeros_like(rgb)
    for rect in profile.keep_regions:
        output[rect.slices()] = rgb[rect.slices()]
    for rect in [*profile.pii_regions, *([profile.face_region] if profile.face_region else [])]:
        output[rect.slices()] = 0
    if not np.any(output):
        return Outcome("MANUAL_REVIEW", "NO_VISIBLE_EVIDENCE", metrics)
    buffer = BytesIO()
    Image.fromarray(output).save(buffer, format="PNG")  # Fresh pixel array: no original metadata.
    content = buffer.getvalue()
    if len(content) > MAX_BYTES:
        return Outcome("MANUAL_REVIEW", "OUTPUT_TOO_LARGE", metrics)
    image = SanitizedImage(content, sha256(content).hexdigest(), profile.id, profile.kind)
    return Outcome("READY", "FIXED_REGIONS_APPLIED", metrics, image)
