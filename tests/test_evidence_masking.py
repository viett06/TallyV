"""Image masking and profile configuration tests."""

import json
import sys
from io import BytesIO

import pytest
from PIL import Image, ImageDraw, PngImagePlugin
from pydantic import ValidationError

from app.services.evidence_masking import ProfileSet, decode, process
from scripts.configure_evidence_privacy import build_profile, main


@pytest.fixture
def reference():
    image = Image.new("RGB", (160, 120), "gray")
    draw = ImageDraw.Draw(image)
    for x in (0, 144):
        draw.rectangle((x, 0, x + 15, 11), fill="blue")
        draw.line((x, 0, x + 15, 11), fill="white", width=2)
    draw.rectangle((30, 20, 85, 90), fill="red")
    draw.text((3, 103), "SECRET_PERSON", fill="white")
    draw.text((112, 35), "ERROR", fill="white")
    info = PngImagePlugin.PngInfo()
    info.add_text("employee", "SECRET_PERSON")
    output = BytesIO()
    image.save(output, format="PNG", pnginfo=info)
    return output.getvalue()


@pytest.fixture
def spec():
    return {
        "id": "sample-device",
        "kind": "FACEID",
        "enabled": True,
        "anchors": [{"rect": {"x": x, "y": 0, "w": 16, "h": 12}} for x in (0, 144)],
        "keep_regions": [{"x": 0, "y": 0, "w": 160, "h": 120}],
        "pii_regions": [{"x": 0, "y": 100, "w": 160, "h": 20}],
        "face_region": {"x": 25, "y": 15, "w": 65, "h": 80},
    }


@pytest.fixture
def layout(reference, spec):
    return build_profile(reference, spec)


def test_masks_fixed_regions_strips_metadata_and_preserves_other_pixels(reference, layout):
    result = process(reference, ProfileSet(profiles=[layout]))
    assert result.status == "READY"
    pixels = decode(result.image.content)
    assert not pixels[15:95, 25:90].any()
    assert not pixels[100:].any()
    assert (pixels[30:50, 110:150] == decode(reference)[30:50, 110:150]).all()
    assert Image.open(BytesIO(result.image.content)).info == {}
    assert Image.open(BytesIO(reference)).info["employee"] == "SECRET_PERSON"


@pytest.mark.parametrize("case", ["no_profile", "disabled", "ambiguous", "corrupt", "resized", "blank"])
def test_unrecognized_input_never_produces_releasable_image(reference, layout, case):
    config = ProfileSet(profiles=[layout])
    if case == "no_profile":
        config = ProfileSet()
    elif case == "disabled":
        layout.enabled = False
    elif case == "ambiguous":
        config.profiles.append(layout.model_copy(update={"id": "duplicate-layout"}))
    elif case == "corrupt":
        reference = b"invalid image"
    else:
        buffer = BytesIO()
        image = Image.new("RGB", (160, 120)) if case == "blank" else Image.open(BytesIO(reference)).resize((80, 60))
        image.save(buffer, format="PNG")
        reference = buffer.getvalue()
    result = process(reference, config)
    assert result.status == "MANUAL_REVIEW" and result.image is None


def test_only_explicit_keep_regions_can_survive(reference, layout):
    layout.keep_regions = [layout.keep_regions[0].model_copy(update={"x": 110, "y": 30, "w": 40, "h": 50})]
    result = process(reference, ProfileSet(profiles=[layout]))
    pixels = decode(result.image.content)
    assert not pixels[:30].any() and not pixels[80:].any() and not pixels[:, :110].any()


def test_anchors_cannot_include_sensitive_regions(reference, spec):
    spec["anchors"][0]["rect"] = {"x": 0, "y": 100, "w": 100, "h": 20}
    with pytest.raises(ValidationError):
        build_profile(reference, spec)


@pytest.mark.parametrize("sensitive", ["face_region", "pii_regions"])
def test_permitted_text_region_cannot_overlap_sensitive_pixels(reference, spec, sensitive):
    spec["keep_text_regions"] = [spec["face_region"]] if sensitive == "face_region" else spec["pii_regions"]
    with pytest.raises(ValidationError, match="must not overlap a face or PII region"):
        build_profile(reference, spec)


def test_cli_builds_disabled_profile_and_local_preview(reference, spec, tmp_path, monkeypatch):
    source, spec_path = tmp_path / "reference.png", tmp_path / "spec.json"
    profiles, preview = tmp_path / "profiles.json", tmp_path / "preview.png"
    source.write_bytes(reference)
    spec["enabled"] = False
    spec_path.write_text(json.dumps(spec))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_evidence_privacy",
            "--reference",
            str(source),
            "--spec",
            str(spec_path),
            "--profiles",
            str(profiles),
            "--preview",
            str(preview),
        ],
    )
    main()
    assert not ProfileSet.model_validate_json(profiles.read_bytes()).profiles[0].enabled
    assert not decode(preview.read_bytes())[100:].any()
    assert source.read_bytes() == reference
