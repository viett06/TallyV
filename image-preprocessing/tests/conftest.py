from io import BytesIO

import pytest
from PIL import Image, ImageDraw, PngImagePlugin
from tallyv_image_preprocessing.cli import build_profile


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
