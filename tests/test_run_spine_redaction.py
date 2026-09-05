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
