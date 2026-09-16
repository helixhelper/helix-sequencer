from __future__ import annotations

import json
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from core.xsq_duration_guard import normalize_xsq_duration


def _write_silence(path: Path, duration_ms: int = 1000) -> None:
    sample_rate = 8000
    frames = int(sample_rate * duration_ms / 1000.0)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\x00\x00" * frames)


def _write_xsq(path: Path, media_name: str) -> None:
    path.write_text(
        (
            "<xsequence>"
            "<head>"
            f"<mediaFile>{media_name}</mediaFile>"
            "<sequenceDuration>999.000</sequenceDuration>"
            "</head>"
            "<ElementEffects>"
            '<Element type="timing" name="Note Onsets"><EffectLayer>'
            '<Effect label="valid" startTime="100" endTime="200" />'
            '<Effect label="clip" startTime="900" endTime="1100" />'
            '<Effect label="stale" startTime="120000" endTime="121000" />'
            "</EffectLayer></Element>"
            '<Element type="model" name="TREE"><EffectLayer>'
            '<Effect name="On" startTime="0" endTime="1000" />'
            '<Effect name="stale-model" startTime="1000" endTime="2000" />'
            "</EffectLayer></Element>"
            "</ElementEffects>"
            "</xsequence>"
        ),
        encoding="utf-8",
    )


def _all_effect_times(path: Path) -> list[tuple[int, int]]:
    root = ET.parse(path).getroot()
    return [
        (int(effect.attrib["startTime"]), int(effect.attrib["endTime"]))
        for effect in root.findall("./ElementEffects//Effect")
    ]


def test_media_duration_removes_stale_template_marks_and_clips_boundary(tmp_path: Path) -> None:
    audio = tmp_path / "song.wav"
    xsq = tmp_path / "song,v27.3.xsq"
    _write_silence(audio, 1000)
    _write_xsq(xsq, audio.name)
    show_manifest = xsq.with_name(f"{xsq.stem}.show.json")
    report = xsq.with_name(f"{xsq.stem}.report.json")
    show_manifest.write_text('{"model_effects": 999, "models_with_effects": 999}', encoding="utf-8")
    report.write_text('{"output_contract": {"model_effects": 999}}', encoding="utf-8")

    summary = normalize_xsq_duration(xsq)

    assert summary["duration_ms"] == 1000
    assert summary["duration_source"] == "media"
    assert summary["removed_effects"] == 2
    assert summary["removed_timing_effects"] == 1
    assert summary["removed_model_effects"] == 1
    assert summary["clipped_effects"] == 1
    assert summary["clipped_timing_effects"] == 1
    assert summary["remaining_out_of_range_effects"] == 0
    assert summary["model_effects_before"] == 2
    assert summary["model_effects_after"] == 1
    assert summary["models_with_effects_after"] == 1
    assert all(start < 1000 and end <= 1000 for start, end in _all_effect_times(xsq))

    manifest_payload = json.loads(show_manifest.read_text(encoding="utf-8"))
    report_payload = json.loads(report.read_text(encoding="utf-8"))
    assert manifest_payload["duration_normalization"]["removed_effects"] == 2
    assert manifest_payload["model_effects"] == 1
    assert manifest_payload["models_with_effects"] == 1
    assert report_payload["output_contract"]["duration_normalization"]["clipped_effects"] == 1
    assert report_payload["output_contract"]["model_effects"] == 1


def test_sequence_duration_is_fallback_when_media_duration_is_unavailable(tmp_path: Path) -> None:
    xsq = tmp_path / "no-media.xsq"
    xsq.write_text(
        (
            "<xsequence><head><sequenceDuration>2.000</sequenceDuration></head>"
            "<ElementEffects><Element type=\"timing\" name=\"Old\"><EffectLayer>"
            '<Effect label="clip" startTime="1900" endTime="2500" />'
            '<Effect label="drop" startTime="2200" endTime="2300" />'
            "</EffectLayer></Element></ElementEffects></xsequence>"
        ),
        encoding="utf-8",
    )

    summary = normalize_xsq_duration(xsq)

    assert summary["duration_ms"] == 2000
    assert summary["duration_source"] == "sequenceDuration"
    assert summary["removed_effects"] == 1
    assert summary["clipped_effects"] == 1
    assert summary["model_effects_before"] == 0
    assert summary["model_effects_after"] == 0
    assert _all_effect_times(xsq) == [(1900, 2000)]


def test_duration_guard_refuses_to_turn_model_sequence_back_into_timing_only(tmp_path: Path) -> None:
    audio = tmp_path / "short.wav"
    xsq = tmp_path / "short,v27.3.xsq"
    _write_silence(audio, 500)
    xsq.write_text(
        (
            "<xsequence><head>"
            f"<mediaFile>{audio.name}</mediaFile>"
            "<sequenceDuration>0.500</sequenceDuration>"
            "</head><ElementEffects>"
            '<Element type="timing" name="AUTO"><EffectLayer>'
            '<Effect label="beat" startTime="100" endTime="200" />'
            "</EffectLayer></Element>"
            '<Element type="model" name="TREE"><EffectLayer>'
            '<Effect name="stale" startTime="700" endTime="900" />'
            "</EffectLayer></Element>"
            "</ElementEffects></xsequence>"
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="removed every model effect"):
        normalize_xsq_duration(xsq)

    # Fail closed before rewriting the original XSQ into a timing-only artifact.
    root = ET.parse(xsq).getroot()
    assert len(root.findall('./ElementEffects/Element[@type="model"]//Effect')) == 1
