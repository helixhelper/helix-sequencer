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


def test_preexisting_recent_xsq_does_not_count_as_fresh_output(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"")
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    existing = output_root / "song,v27.3.xsq"
    existing.write_text("<xsequence />", encoding="utf-8")

    monkeypatch.setattr(effect_engine_beat_grid.effect_engine, "main_for", lambda _version, _argv: None)

    with pytest.raises(RuntimeError, match="returned without producing a fresh XSQ"):
        effect_engine_beat_grid.main_for(
            "v27.3",
            ["--audio", str(audio), "--output-dir", str(output_root)],
        )


def test_existing_xsq_that_changes_during_run_counts_as_fresh(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"")
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    existing = output_root / "song,v27.3.xsq"
    existing.write_text("old", encoding="utf-8")

    def fake_main_for(_version: str, _argv: list[str]) -> None:
        existing.write_text("new sequence content", encoding="utf-8")

    monkeypatch.setattr(effect_engine_beat_grid.effect_engine, "main_for", fake_main_for)

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


def test_main_for_promotes_swallowed_failed_log_even_when_xsq_exists(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"")
    output_root = tmp_path / "outputs"

    def quiet_log(_message: str) -> None:
        return None

    def fake_main_for(_version: str, _argv: list[str]) -> None:
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "song,v27.3.xsq").write_text("<xsequence />", encoding="utf-8")
        effect_engine_beat_grid.effect_engine.log("FAILED: song.wav: RuntimeError('post-generation failure')")

    monkeypatch.setattr(effect_engine_beat_grid.effect_engine, "log", quiet_log)
    monkeypatch.setattr(effect_engine_beat_grid.effect_engine, "main_for", fake_main_for)

    with pytest.raises(RuntimeError, match="reported generation failure"):
        effect_engine_beat_grid.main_for(
            "v27.3",
            ["--audio", str(audio), "--output-dir", str(output_root)],
        )

    assert effect_engine_beat_grid.effect_engine.log is quiet_log


def test_beat_grid_postprocess_is_scoped_to_configured_output_root(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"")
    output_root = tmp_path / "outputs"
    scanned_roots: list[Path] = []

    def fake_main_for(_version: str, _argv: list[str]) -> None:
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "song,v27.3.xsq").write_text("<xsequence />", encoding="utf-8")

    def fake_postprocess(root: Path, beat_grid, *, since: float | None = None) -> dict[str, object]:
        scanned_roots.append(root)
        return {
            "enabled": True,
            "reports_touched": 0,
            "snowman_exports_touched": 0,
            "root": str(root.resolve()),
            "subdivision": beat_grid.subdivision,
            "mode": beat_grid.mode,
        }

    monkeypatch.setattr(effect_engine_beat_grid.effect_engine, "main_for", fake_main_for)
    monkeypatch.setattr(effect_engine_beat_grid.effect_engine, "log", lambda _message: None)
    monkeypatch.setattr(effect_engine_beat_grid, "postprocess_beat_grid_outputs", fake_postprocess)

    effect_engine_beat_grid.main_for(
        "v27.3",
        [
            "--snap-grid",
            "16",
            "--snap-bpm",
            "120",
            "--audio",
            str(audio),
            "--output-dir",
            str(output_root),
        ],
    )

    assert scanned_roots == [output_root]
