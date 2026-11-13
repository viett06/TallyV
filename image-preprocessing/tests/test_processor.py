"""Standalone package tests: no TallyV settings, database, FastAPI or queue."""

import asyncio
import subprocess
import sys
import threading
from io import BytesIO

import pytest
import tallyv_image_preprocessing as preprocessing
from PIL import Image
from pydantic import ValidationError
from tallyv_image_preprocessing import ProfileSet, process, process_async
from tallyv_image_preprocessing.processor import decode


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
    from tallyv_image_preprocessing.cli import build_profile

    spec["anchors"][0]["rect"] = {"x": 0, "y": 100, "w": 100, "h": 20}
    with pytest.raises(ValidationError):
        build_profile(reference, spec)


def test_async_api_preserves_result(reference, layout):
    config = ProfileSet(profiles=[layout])
    result = asyncio.run(process_async(reference, config))
    assert result == process(reference, config)


def test_async_api_does_not_block_event_loop(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    thread_ids = []

    def work(*args):
        thread_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(timeout=2)
        return "finished"

    monkeypatch.setattr(preprocessing, "process", work)

    async def scenario():
        task = asyncio.create_task(process_async(b"", ProfileSet()))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            await asyncio.sleep(0)
            assert not task.done()
            assert thread_ids[0] != threading.get_ident()
        finally:
            release.set()
        assert await task == "finished"

    asyncio.run(scenario())


def test_can_import_outside_tallyv_repository(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import tallyv_image_preprocessing; assert 'app' not in sys.modules"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
