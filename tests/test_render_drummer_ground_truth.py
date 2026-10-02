from __future__ import annotations

from PIL import ImageChops

from tools.render_drummer_v3_preview import (
    DOWNBEAT_COMPONENTS,
    DOWNBEAT_OVERLAY_KEY,
    LAYER_BY_TARGET,
    SOURCE_IMAGE,
    _detect_kit_panel,
    compose_drummer_frame,
    prepare_visual_assets,
)


def test_renderer_uses_approved_source_and_all_eight_layers() -> None:
    assert SOURCE_IMAGE.name == "drummerbg.png"
    assert SOURCE_IMAGE.exists()
    assert len(LAYER_BY_TARGET) == 8


def test_each_approved_hit_layer_changes_the_ground_truth_frame() -> None:
    base, overlays = prepare_visual_assets(320, 180)
    assert base.getbbox() is not None
    assert set(LAYER_BY_TARGET) <= set(overlays)
    assert DOWNBEAT_OVERLAY_KEY in overlays

    base_rgb = base.convert("RGB")
    for target in LAYER_BY_TARGET:
        frame = compose_drummer_frame(
            base,
            overlays,
            {name: 1.0 if name == target else 0.0 for name in LAYER_BY_TARGET},
        )
        diff = ImageChops.difference(base_rgb, frame)
        assert diff.getbbox() is not None, target


def test_downbeat_signature_adds_approved_impact_overlay() -> None:
    base, overlays = prepare_visual_assets(320, 180)
    active = {name: 0.0 for name in LAYER_BY_TARGET}
    for component in DOWNBEAT_COMPONENTS:
        active[component] = 1.0
    frame = compose_drummer_frame(base, overlays, active)
    assert ImageChops.difference(base.convert("RGB"), frame).getbbox() is not None


def test_hit_overlays_are_aligned_to_black_kit_panel() -> None:
    from PIL import Image

    width, height = 320, 180
    with Image.open(SOURCE_IMAGE) as source:
        source = source.convert("RGBA")
        panel = _detect_kit_panel(source)
        scale = min(width / source.width, height / source.height)
        fitted_w = round(source.width * scale)
        fitted_h = round(source.height * scale)
        offset_x = (width - fitted_w) // 2
        offset_y = (height - fitted_h) // 2
        panel_out = (
            offset_x + round(panel[0] * scale),
            offset_y + round(panel[1] * scale),
            offset_x + round(panel[2] * scale),
            offset_y + round(panel[3] * scale),
        )

    _, overlays = prepare_visual_assets(width, height)
    margin = 12
    for target in LAYER_BY_TARGET:
        bbox = overlays[target].getbbox()
        assert bbox is not None, target
        assert bbox[0] >= panel_out[0] - margin, (target, bbox, panel_out)
        assert bbox[1] >= panel_out[1] - margin, (target, bbox, panel_out)
        assert bbox[2] <= panel_out[2] + margin, (target, bbox, panel_out)
        assert bbox[3] <= panel_out[3] + margin, (target, bbox, panel_out)
