from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "fixtures" / "band_geometry" / "drummer_v3_png_layer_manifest.json"

REQUIRED_FRAMES = {
    "idle_ready",
    "kick",
    "snare",
    "hi_hat",
    "left_tom",
    "right_tom",
    "left_cymbal",
    "right_cymbal",
    "both_cymbals",
    "downbeat",
}


def test_drummer_v3_manifest_declares_png_input_and_frames() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["source_image"] == "fixtures/band_geometry/source/drummerbg.png"
    assert set(manifest["required_frames"]) == REQUIRED_FRAMES
    assert len(manifest["layers"]) == 9

    layer_ids = {layer["id"] for layer in manifest["layers"]}
    assert REQUIRED_FRAMES - {"idle_ready"} <= layer_ids

    for layer in manifest["layers"]:
        assert layer["file"].endswith(".png")
        assert layer["target_components"]
        assert layer["contact_components"]
        assert layer["commands"]
