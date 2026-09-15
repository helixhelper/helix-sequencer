from __future__ import annotations

from core.snowman_band import _build_intelligent_drum_cues


def test_legacy_marks_flow_through_pose_aware_drummer_path() -> None:
    cues, kit, debug = _build_intelligent_drum_cues(
        [],
        drum_event_streams=None,
        kicks=[100],
        snares=[220],
        hats=[340],
        releases=[460],
    )

    assert debug["fallback_mode"] == "legacy_marks"
    assert debug["pose_mapping"]
    assert {"kick", "snare", "hihat", "cymbal"} <= set(kit)
    assert all(cue["pose"] for cue in cues)
    assert all(cue["xlights_model"] == "HX_SNOWMAN_DRUMMER" for cue in cues)
    assert all(cue["xlights_submodels"] for cue in cues)
    assert all(cue["motion"] for cue in cues)
