from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import engine_profiles
from tools import build_outcome_preview_manifest as preview_manifest


def _write_large(path: Path, content: str) -> None:
    padding = "\n" + (" " * 1200)
    path.write_text(content + padding, encoding="utf-8")


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    version = engine_profiles.active_profile().version
    stem = f"helix-outcome-preview,{version}"
    return (
        tmp_path / f"{stem}.mp4",
        tmp_path / f"{stem}.xsq",
        tmp_path / f"{stem}.report.json",
    )


def _show_path(tmp_path: Path) -> Path:
    version = engine_profiles.active_profile().version
    return tmp_path / f"helix-outcome-preview,{version}.show.json"


def _write_valid_bundle_files(
    tmp_path: Path,
    *,
    effect_end_ms: int = 30000,
    drummer: bool = False,
) -> tuple[Path, Path, Path]:
    mp4, xsq, report = _paths(tmp_path)
    mp4.write_bytes(b"0" * 2048)
    drummer_track = ""
    drummer_row = ""
    if drummer:
        drummer_track = (
            '<Element type="timing" name="AUTO Drummer v27.3"><EffectLayer>'
            '<Effect label="kick:kick_hit" startTime="500" endTime="650" />'
            "</EffectLayer></Element>"
        )
        drummer_row = (
            '<Element type="model" name="HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_HIT_KICK">'
            '<EffectLayer><Effect name="On" startTime="500" endTime="650" /></EffectLayer>'
            "</Element>"
        )
    _write_large(
        xsq,
        (
            "<xsequence><head><sequenceDuration>30.000</sequenceDuration></head>"
            "<ElementEffects><Element type=\"model\" name=\"TREE\"><EffectLayer>"
            f'<Effect name="On" startTime="0" endTime="{effect_end_ms}" />'
            "</EffectLayer></Element>"
            f"{drummer_track}{drummer_row}"
            "</ElementEffects></xsequence>"
        ),
    )
    payload: dict[str, object] = {
        "quality": {
            "score": 90.0,
            "grade": "A",
            "top_show_benchmark": {"score": 91.0, "grade": "A"},
        },
        "padding": "x" * 1400,
    }
    if drummer:
        payload["drummer"] = {
            "analyzed_cues": 1,
            "placement_requests": 1,
            "placed_effects": 1,
            "timing_track_events": 1,
            "review": {
                "placed_cues": 1,
                "unplaced_cues": 0,
                "cue_placement_ratio": 1.0,
            },
        }
        _show_path(tmp_path).write_text(
            json.dumps(
                {
                    "general_effects_added": 0,
                    "drummer_model_effects": 1,
                    "auto_drummer_timing_events": 1,
                    "drummer": {
                        "timing_events": 1,
                        "placed_effects": 1,
                        "placed_by_type": {"kick": 1},
                    },
                    "padding": "x" * 1200,
                }
            ),
            encoding="utf-8",
        )
    report.write_text(json.dumps(payload), encoding="utf-8")
    return mp4, xsq, report


def test_xsq_contract_counts_effects_beyond_declared_duration(tmp_path: Path) -> None:
    _mp4, xsq, _report = _write_valid_bundle_files(tmp_path, effect_end_ms=132050)

    contract = preview_manifest.read_xsq_duration_contract(xsq)

    assert contract["sequence_duration_seconds"] == 30.0
    assert contract["max_effect_end_seconds"] == pytest.approx(132.05)
    assert contract["out_of_declared_range_effects"] == 1.0


def test_manifest_rejects_rendered_preview_that_runs_far_past_benchmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_valid_bundle_files(tmp_path)
    monkeypatch.setattr(
        preview_manifest,
        "_read_video_metadata",
        lambda _path: {"duration": 114.9, "fps": 10.0},
    )
    monkeypatch.setattr(preview_manifest, "_validate_audio_stream", lambda _path: None)

    with pytest.raises(preview_manifest.PreviewArtifactError, match="extends beyond the benchmark"):
        preview_manifest.build_manifest(
            tmp_path,
            benchmark_duration_seconds=30.0,
            event="test",
            commit="deadbeef",
        )


def test_manifest_accepts_bounded_preview_and_records_duration_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_valid_bundle_files(tmp_path)
    monkeypatch.setattr(
        preview_manifest,
        "_read_video_metadata",
        lambda _path: {"duration": 30.0, "fps": 10.0},
    )
    monkeypatch.setattr(preview_manifest, "_validate_audio_stream", lambda _path: None)

    manifest = preview_manifest.build_manifest(
        tmp_path,
        benchmark_duration_seconds=30.0,
        event="test",
        commit="deadbeef",
    )

    assert manifest["rendered_duration_seconds"] == 30.0
    assert manifest["sequence_duration_seconds"] == 30.0
    assert manifest["max_effect_end_seconds"] == 30.0
    assert manifest["out_of_declared_range_effects"] == 0
    assert manifest["maximum_allowed_duration_seconds"] == pytest.approx(31.75)
    assert manifest["drummer"]["required"] is False
    assert manifest["general_recovery_effects"] == 0


def test_manifest_rejects_required_drummer_preview_without_render_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_valid_bundle_files(tmp_path)
    monkeypatch.setattr(
        preview_manifest,
        "_read_video_metadata",
        lambda _path: {"duration": 30.0, "fps": 10.0},
    )
    monkeypatch.setattr(preview_manifest, "_validate_audio_stream", lambda _path: None)

    with pytest.raises(preview_manifest.PreviewArtifactError, match="Preview proof requires"):
        preview_manifest.build_manifest(
            tmp_path,
            benchmark_duration_seconds=30.0,
            event="test",
            commit="deadbeef",
            require_drummer=True,
        )


def test_manifest_accepts_required_drummer_preview_with_cross_checked_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_valid_bundle_files(tmp_path, drummer=True)
    monkeypatch.setattr(
        preview_manifest,
        "_read_video_metadata",
        lambda _path: {"duration": 30.0, "fps": 10.0},
    )
    monkeypatch.setattr(preview_manifest, "_validate_audio_stream", lambda _path: None)

    manifest = preview_manifest.build_manifest(
        tmp_path,
        benchmark_duration_seconds=30.0,
        event="test",
        commit="deadbeef",
        require_drummer=True,
    )

    drummer = manifest["drummer"]
    assert drummer["required"] is True
    assert drummer["analyzed_cues"] == 1
    assert drummer["placement_requests"] == 1
    assert drummer["report_placed_effects"] == 1
    assert drummer["report_timing_track_events"] == 1
    assert drummer["show_drummer_model_effects"] == 1
    assert drummer["show_auto_drummer_timing_events"] == 1


def test_manifest_rejects_missing_required_drum_classes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_valid_bundle_files(tmp_path, drummer=True)
    monkeypatch.setattr(
        preview_manifest,
        "_read_video_metadata",
        lambda _path: {"duration": 30.0, "fps": 10.0},
    )
    monkeypatch.setattr(preview_manifest, "_validate_audio_stream", lambda _path: None)

    with pytest.raises(preview_manifest.PreviewArtifactError, match="class coverage is incomplete"):
        preview_manifest.build_manifest(
            tmp_path,
            benchmark_duration_seconds=30.0,
            event="test",
            commit="deadbeef",
            require_drummer=True,
            require_drum_classes=True,
        )


def test_manifest_accepts_all_required_drum_classes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_valid_bundle_files(tmp_path, drummer=True)
    show = json.loads(_show_path(tmp_path).read_text(encoding="utf-8"))
    show["drummer"]["placed_by_type"] = {
        "kick": 3,
        "snare": 2,
        "hihat": 4,
        "tom": 1,
        "cymbal": 2,
    }
    _show_path(tmp_path).write_text(json.dumps(show), encoding="utf-8")
    monkeypatch.setattr(
        preview_manifest,
        "_read_video_metadata",
        lambda _path: {"duration": 30.0, "fps": 10.0},
    )
    monkeypatch.setattr(preview_manifest, "_validate_audio_stream", lambda _path: None)

    manifest = preview_manifest.build_manifest(
        tmp_path,
        benchmark_duration_seconds=30.0,
        event="test",
        commit="deadbeef",
        require_drummer=True,
        require_drum_classes=True,
    )

    assert all(manifest["drummer"]["placed_by_type"][key] > 0 for key in preview_manifest.REQUIRED_DRUM_TYPES)


def test_manifest_rejects_beta_recovery_when_native_choreography_is_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_valid_bundle_files(tmp_path, drummer=True)
    show = json.loads(_show_path(tmp_path).read_text(encoding="utf-8"))
    show["general_effects_added"] = 12
    _show_path(tmp_path).write_text(json.dumps(show), encoding="utf-8")
    monkeypatch.setattr(
        preview_manifest,
        "_read_video_metadata",
        lambda _path: {"duration": 30.0, "fps": 10.0},
    )
    monkeypatch.setattr(preview_manifest, "_validate_audio_stream", lambda _path: None)

    with pytest.raises(preview_manifest.PreviewArtifactError, match="relied on beta recovery choreography"):
        preview_manifest.build_manifest(
            tmp_path,
            benchmark_duration_seconds=30.0,
            event="test",
            commit="deadbeef",
            require_native_choreography=True,
        )
