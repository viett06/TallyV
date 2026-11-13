import json
import sys

from tallyv_image_preprocessing import ProfileSet
from tallyv_image_preprocessing.cli import main
from tallyv_image_preprocessing.processor import decode


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
            "image-privacy-profile",
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
