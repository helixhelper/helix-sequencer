from __future__ import annotations

from PIL import ImageChops

from tools.render_drummer_v3_preview import (
    LAYER_BY_TARGET,
    SOURCE_IMAGE,
    compose_drummer_frame,
    prepare_visual_assets,
)


def test_renderer_uses_approved_source_and_all_eight_layers() -> None:
    assert SOURCE_IMAGE.name == "drummerbg.png"
    assert SOURCE_IMAGE.exists()
    assert len(LAYER_BY_TARGET) == 8
    assert all(path.exists() for path in LAYER_BY_TARGET.values())


def test_each_approved_hit_layer_changes_the_ground_truth_frame() -> None:
    base, overlays = prepare_visual_assets(320, 180)
    assert base.getbbox() is not None
    assert set(overlays) == set(LAYER_BY_TARGET)

    base_rgb = base.convert("RGB")
    for target in LAYER_BY_TARGET:
        frame = compose_drummer_frame(
            base,
            overlays,
            {name: 1.0 if name == target else 0.0 for name in LAYER_BY_TARGET},
        )
        diff = ImageChops.difference(base_rgb, frame)
        assert diff.getbbox() is not None, target
