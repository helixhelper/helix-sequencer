from __future__ import annotations

from core.drummer_xlights import build_drummer_review, build_timing_track, translate_drummer_cues


def _cue(**overrides: object) -> dict[str, object]:
    cue: dict[str, object] = {
        "start_ms": 100,
        "end_ms": 260,
        "kind": "snare",
        "pose": "snare_hit",
        "velocity": 0.82,
        "confidence": 0.74,
        "xlights_model": "HX_SNOWMAN_DRUMMER",
        "xlights_submodels": ["HX_SNOWMAN_DRUMMER_HIT_SNARE"],
        "source_model": "HX_SNOWMAN_DRUMMER_V3",
        "source_submodels": ["HX_SNOWMAN_DRUMMER_V3_HIT_SNARE"],
    }
    cue.update(overrides)
    return cue


def test_prefers_authored_v3_pose_submodel() -> None:
    target = "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_HIT_SNARE"
    placements = translate_drummer_cues([_cue()], available_targets=[target])

    assert len(placements) == 1
    assert placements[0]["target"] == target
    assert placements[0]["target_tier"] == "v3_pose"
    assert placements[0]["effect"] == "On"
    assert placements[0]["stem"] == "drums"


def test_falls_back_to_v2_kit_parts_when_pose_composite_is_absent() -> None:
    available = [
        "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_SNARE",
        "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_SNARE_RIM",
        "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_LEFT_STICK",
    ]
    placements = translate_drummer_cues([_cue(xlights_submodels=[], source_submodels=[])], available_targets=available)

    assert {item["target"] for item in placements} == set(available)
    assert {item["target_tier"] for item in placements} == {"v2_parts"}


def test_uses_root_model_as_last_resort_and_builds_timing_track() -> None:
    placements = translate_drummer_cues(
        [_cue(xlights_submodels=[], source_submodels=[])],
        available_targets=["HX_SNOWMAN_DRUMMER"],
    )

    assert len(placements) == 1
    assert placements[0]["target_tier"] == "root_model"
    assert build_timing_track(placements) == [("snare:snare_hit", 100, 260)]


def test_returns_no_placements_when_layout_has_no_drummer_rows() -> None:
    assert translate_drummer_cues([_cue()], available_targets=["House", "MegaTree"]) == []


def test_builds_hit_level_review_for_gui_and_audit() -> None:
    kick = _cue(
        start_ms=120,
        end_ms=280,
        kind="kick",
        pose="kick_hit",
        velocity=0.91,
        confidence=0.83,
        source="drummer_x_hybrid",
    )
    snare = _cue(
        start_ms=420,
        end_ms=560,
        kind="snare",
        pose="snare_hit",
        velocity=0.68,
        confidence=0.42,
        source="legacy_drum_marks",
    )
    review = build_drummer_review(
        [kick, snare],
        [
            {
                "start_ms": 120,
                "end_ms": 280,
                "drum_type": "kick",
                "pose": "kick_hit",
                "target": "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_HIT_KICK",
                "target_tier": "v3_pose",
                "placed": True,
            }
        ],
    )

    assert review["analysis_profile"] == "drummer_x_hybrid"
    assert review["counts_by_type"]["kick"] == 1
    assert review["counts_by_type"]["snare"] == 1
    assert review["placed_cues"] == 1
    assert review["unplaced_cues"] == 1
    assert review["low_confidence_events"] == 1
    assert review["events"][0]["placed"] is True
    assert review["events"][1]["placed"] is False
