"""Exact-layout masking. Unknown, ambiguous or unreadable inputs never pass."""

from base64 import b64decode
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
from math import ceil, floor
from typing import Literal

import cv2
import numpy as np
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "fixed-layout-ocr-v2"
MAX_BYTES = 8 * 1024 * 1024
OCR_APPLIED = "LAYOUT_AND_OCR_APPLIED"
TextBox = tuple[float, float, float, float]


class Rect(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)

    def slices(self):
        return slice(self.y, self.y + self.h), slice(self.x, self.x + self.w)

    def contains(self, other: "Rect") -> bool:
        return (
            self.x <= other.x
            and self.y <= other.y
            and self.x + self.w >= other.x + other.w
            and self.y + self.h >= other.y + other.h
        )

    def overlaps(self, other: "Rect") -> bool:
        return (
            self.x < other.x + other.w
            and other.x < self.x + self.w
            and self.y < other.y + other.h
            and other.y < self.y + self.h
        )


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
    keep_text_regions: list[Rect] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def valid_geometry(self):
        if self.width * self.height > 16_000_000:
            raise ValueError("Profile exceeds pixel limit")
        if self.kind == "FACEID" and self.face_region is None:
            raise ValueError("FACEID requires a conservative fixed face region")
        if any(not any(keep.contains(text) for keep in self.keep_regions) for text in self.keep_text_regions):
            raise ValueError("A permitted text region must be inside a keep region")
        sensitive_regions = list(self.pii_regions)
        if self.face_region:
            sensitive_regions.append(self.face_region)
        if any(text.overlaps(sensitive) for text in self.keep_text_regions for sensitive in sensitive_regions):
            raise ValueError("A permitted text region must not overlap a face or PII region")
        rectangles = [*self.keep_regions, *sensitive_regions, *(a.rect for a in self.anchors)]
        for rect in rectangles:
            if rect.x + rect.w > self.width or rect.y + rect.h > self.height:
                raise ValueError("Rectangle outside profile dimensions")
        for anchor in self.anchors:
            patch = anchor.pixels()
            if anchor.rect.w * anchor.rect.h < 64 or float(patch.std(axis=(0, 1)).max()) < 5:
                raise ValueError("Anchors must contain distinctive static UI detail")
            if any(anchor.rect.overlaps(region) for region in sensitive_regions):
                raise ValueError("Static anchors must not contain a PII or face region")
        for i, first in enumerate(self.anchors):
            for second in self.anchors[i + 1 :]:
                if first.rect.overlaps(second.rect):
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
class LayoutImage:
    content: bytes = field(repr=False)
    sha256: str
    profile_id: str
    kind: str


@dataclass(frozen=True)
class SanitizedImage(LayoutImage):
    """Image produced after both layout masking and local OCR."""


@dataclass(frozen=True)
class Outcome:
    status: Literal["READY", "MANUAL_REVIEW"]
    reason: str
    metrics: dict = field(default_factory=dict)
    image: LayoutImage | None = None


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


def _encode(rgb: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG")
    return buffer.getvalue()


def _mask_text(rgb: np.ndarray, boxes: list[TextBox], keep: list[Rect]) -> None:
    height, width = rgb.shape[:2]
    for left, top, right, bottom in boxes:
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError("OCR returned invalid text coordinates")
        x, y = max(0, floor(left * width) - 2), max(0, floor(top * height) - 2)
        end_x, end_y = min(width, ceil(right * width) + 2), min(height, ceil(bottom * height) + 2)
        rect = Rect(x=x, y=y, w=end_x - x, h=end_y - y)
        if not any(region.contains(rect) for region in keep):
            rgb[rect.slices()] = 0


def process(
    content: bytes,
    profiles: ProfileSet,
    *,
    detect_text: Callable[[bytes], list[TextBox]] | None = None,
) -> Outcome:
    """Mask the known layout, then optionally redact OCR boxes on those pixels."""
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
    content = _encode(output)  # Fresh pixel array: no original metadata.
    if len(content) > MAX_BYTES:
        return Outcome("MANUAL_REVIEW", "OUTPUT_TOO_LARGE", metrics)
    if detect_text is None:
        preview = LayoutImage(content, sha256(content).hexdigest(), profile.id, profile.kind)
        return Outcome("READY", "FIXED_REGIONS_APPLIED", metrics, preview)
    _mask_text(output, detect_text(content), profile.keep_text_regions)
    if not np.any(output):
        return Outcome("MANUAL_REVIEW", "NO_VISIBLE_EVIDENCE", metrics)
    content = _encode(output)
    if len(content) > MAX_BYTES:
        return Outcome("MANUAL_REVIEW", "OUTPUT_TOO_LARGE", metrics)
    image = SanitizedImage(content, sha256(content).hexdigest(), profile.id, profile.kind)
    return Outcome("READY", OCR_APPLIED, metrics, image)
