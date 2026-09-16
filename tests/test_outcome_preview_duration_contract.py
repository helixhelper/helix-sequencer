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


def _write_valid_bundle_files(tmp_path: Path, *, effect_end_ms: int = 30000) -> tuple[Path, Path, Path]:
    mp4, xsq, report = _paths(tmp_path)
    mp4.write_bytes(b"0" * 2048)
    _write_large(
        xsq,
        (
            "<xsequence><head><sequenceDuration>30.000</sequenceDuration></head>"
            "<ElementEffects><Element type=\"model\" name=\"TREE\"><EffectLayer>"
            f'<Effect name="On" startTime="0" endTime="{effect_end_ms}" />'
            "</EffectLayer></Element></ElementEffects></xsequence>"
        ),
    )
    payload = {
        "quality": {
            "score": 90.0,
            "grade": "A",
            "top_show_benchmark": {"score": 91.0, "grade": "A"},
        },
        "padding": "x" * 1400,
    }
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
