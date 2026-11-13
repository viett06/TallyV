"""Build an offline layout profile from manually selected regions. No models/HTTP."""

import argparse
import json
from base64 import b64encode
from pathlib import Path

from tallyv_image_preprocessing.processor import LayoutProfile, ProfileSet, Rect, decode, process


def build_profile(reference: bytes, spec: dict) -> LayoutProfile:
    rgb = decode(reference)
    spec = dict(spec)
    spec.setdefault("width", rgb.shape[1])
    spec.setdefault("height", rgb.shape[0])
    if (spec["height"], spec["width"]) != rgb.shape[:2]:
        raise ValueError("Reference dimensions differ from the profile")
    anchors = []
    for item in spec["anchors"]:
        item = dict(item)
        rect = Rect.model_validate(item["rect"])
        item["rgb_base64"] = b64encode(rgb[rect.slices()].tobytes()).decode("ascii")
        anchors.append(item)
    spec["anchors"] = anchors
    return LayoutProfile.model_validate(spec)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--preview", required=True, type=Path)
    args = parser.parse_args()
    content = args.reference.read_bytes()
    profile = build_profile(content, json.loads(args.spec.read_text()))
    existing = ProfileSet.model_validate_json(args.profiles.read_bytes()) if args.profiles.exists() else ProfileSet()
    updated = ProfileSet(profiles=[p for p in existing.profiles if p.id != profile.id] + [profile])
    preview = process(content, ProfileSet(profiles=[profile.model_copy(update={"enabled": True})]))
    if preview.image is None:
        raise ValueError("Profile leaves no visible evidence")
    args.preview.write_bytes(preview.image.content)
    temporary = args.profiles.with_suffix(args.profiles.suffix + ".tmp")
    temporary.write_text(updated.model_dump_json(indent=2) + "\n")
    temporary.replace(args.profiles)
    print(f"Profile {profile.id}: enabled={profile.enabled}; sanitized preview generated. No inference performed.")


if __name__ == "__main__":
    main()
