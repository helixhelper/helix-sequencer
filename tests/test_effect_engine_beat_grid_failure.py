from __future__ import annotations

from pathlib import Path

import pytest

from core import effect_engine_beat_grid


def test_requested_audio_paths_supports_batch_and_inline_forms() -> None:
    requested = effect_engine_beat_grid._requested_audio_paths(
        ["--audio", "one.wav", "two.mp3", "--template", "template.xsq", "--audio=three.flac"]
    )

    assert requested == [Path("one.wav"), Path("two.mp3"), Path("three.flac")]


def test_main_for_raises_when_engine_returns_without_requested_output(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"")
    output_root = tmp_path / "outputs"

    monkeypatch.setattr(effect_engine_beat_grid.effect_engine, "main_for", lambda _version, _argv: None)

    with pytest.raises(RuntimeError, match="returned without producing a fresh XSQ"):
        effect_engine_beat_grid.main_for(
            "v27.3",
            ["--audio", str(audio), "--output-dir", str(output_root)],
        )


def test_main_for_reports_only_missing_song_from_partial_batch(tmp_path, monkeypatch) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    first.write_bytes(b"")
    second.write_bytes(b"")
    output_root = tmp_path / "outputs"

    def fake_main_for(_version: str, _argv: list[str]) -> None:
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "first,v27.3.xsq").write_text("<xsequence />", encoding="utf-8")

    monkeypatch.setattr(effect_engine_beat_grid.effect_engine, "main_for", fake_main_for)

    with pytest.raises(RuntimeError) as exc_info:
        effect_engine_beat_grid.main_for(
            "v27.3",
            ["--audio", str(first), str(second), "--output-dir", str(output_root)],
        )

    message = str(exc_info.value)
    assert str(second) in message
    assert str(first) not in message
