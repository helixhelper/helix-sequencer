from __future__ import annotations

import json
from pathlib import Path

from core.run_spine import REDACTED_VALUE, RunConfig, RunManager


def test_legacy_run_manager_redacts_secret_from_default_command_and_failures(tmp_path: Path) -> None:
    secret = "legacy-super-secret-key"
    config = RunConfig.from_engine_args(
        "master",
        [
            "--output-dir",
            str(tmp_path / "outputs"),
            "--moises-api-key",
            secret,
            "--audio",
            "song.wav",
        ],
    )

    manager = RunManager(config)
    manager.record_warning(f"warning echoed {secret}")
    manager.record_error(f"error echoed {secret}")
    manager.finalize(False, f"fatal error echoed {secret}")

    command_text = manager.command_path.read_text(encoding="utf-8")
    manifest_text = manager.manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    assert secret not in command_text
    assert secret not in manifest_text
    assert REDACTED_VALUE in command_text
    assert REDACTED_VALUE in manifest["command"]
    assert REDACTED_VALUE in manifest["warnings"][0]
    assert REDACTED_VALUE in manifest["errors"][0]
    assert REDACTED_VALUE in manifest["error_summary"]


def test_legacy_run_manager_redacts_inline_secret_from_custom_command(tmp_path: Path) -> None:
    secret = "inline-legacy-secret"
    config = RunConfig(output_root=tmp_path / "outputs")
    manager = RunManager(config, command=["main.py", f"--moises-api-key={secret}"])

    assert secret not in manager.command_path.read_text(encoding="utf-8")
    assert secret not in manager.manifest_path.read_text(encoding="utf-8")
    assert f"--moises-api-key={REDACTED_VALUE}" in manager.command


def test_inline_power_metadata_does_not_skip_following_option(tmp_path: Path) -> None:
    metadata = tmp_path / "power.json"
    config = RunConfig.from_engine_args(
        "master",
        [
            f"--power-metadata-file={metadata}",
            "--autosize-controllers",
            "--controller-padding=75",
        ],
    )

    assert config.power_metadata_path == metadata
    assert config.autosize_controllers is True
    assert config.controller_padding == 75


def test_run_config_preserves_all_batch_audio_paths() -> None:
    config = RunConfig.from_engine_args(
        "master",
        [
            "--audio",
            "first.wav",
            "second.mp3",
            "third.flac",
            "--variants",
            "2",
        ],
    )

    assert config.audio_path == Path("first.wav")
    assert config.audio_paths == (Path("first.wav"), Path("second.mp3"), Path("third.flac"))
    assert config.resolved_audio_paths() == config.audio_paths
    assert config.to_engine_args()[:4] == ["--audio", "first.wav", "second.mp3", "third.flac"]
    assert config.variants == 2


def test_run_config_appends_repeated_and_inline_audio_flags() -> None:
    config = RunConfig.from_engine_args(
        "master",
        [
            "--audio=first.wav",
            "--audio",
            "second.mp3",
            "third.flac",
            "--layout-file",
            "layout.xml",
        ],
    )

    assert config.audio_paths == (Path("first.wav"), Path("second.mp3"), Path("third.flac"))
    assert config.audio_path == Path("first.wav")
    assert config.layout_path == Path("layout.xml")


def test_run_manifest_records_every_requested_audio(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    config = RunConfig.from_engine_args(
        "master",
        [
            "--output-dir",
            str(output_root),
            "--audio",
            "first.wav",
            "second.mp3",
        ],
    )

    manager = RunManager(config)
    manifest = json.loads(manager.manifest_path.read_text(encoding="utf-8"))

    assert manifest["audio_path"] == "first.wav"
    assert manifest["audio_paths"] == ["first.wav", "second.mp3"]


def test_run_manager_ids_are_collision_safe_within_same_second(tmp_path: Path) -> None:
    config = RunConfig(output_root=tmp_path / "outputs")

    first = RunManager(config)
    second = RunManager(config)

    assert first.run_id != second.run_id
    assert first.run_dir != second.run_dir
    assert first.run_dir.is_dir()
    assert second.run_dir.is_dir()
