from __future__ import annotations

import json
from pathlib import Path

from core.run_config import RunConfig
from core.run_manager import (
    REDACTED_VALUE,
    RunManager,
    _extract_sensitive_values,
    _redact_command_parts,
    _redact_command_text,
    _redact_runtime_text,
)


def test_redact_command_parts_handles_separate_and_inline_api_keys() -> None:
    secret = "super-secret-key"

    assert _redact_command_parts(["main.py", "--moises-api-key", secret, "--audio", "song.wav"]) == [
        "main.py",
        "--moises-api-key",
        REDACTED_VALUE,
        "--audio",
        "song.wav",
    ]
    assert _redact_command_parts(["main.py", f"--moises-api-key={secret}"]) == [
        "main.py",
        f"--moises-api-key={REDACTED_VALUE}",
    ]


def test_redact_command_text_hides_api_key() -> None:
    secret = "super-secret-key"
    redacted = _redact_command_text(f"python main.py --moises-api-key {secret} --audio song.wav")

    assert secret not in redacted
    assert f"--moises-api-key {REDACTED_VALUE}" in redacted


def test_extract_sensitive_values_and_runtime_redaction_support_string_commands() -> None:
    secret = "super-secret-key"
    values = _extract_sensitive_values(f"python main.py --moises-api-key='{secret}' --audio song.wav")

    assert values == (secret,)
    redacted = _redact_runtime_text(f"request failed while using key {secret}", values)
    assert secret not in redacted
    assert REDACTED_VALUE in redacted


def test_run_manager_never_writes_cli_api_key_to_command_or_manifest(tmp_path: Path) -> None:
    secret = "super-secret-key"
    config = RunConfig(output_root=tmp_path / "outputs")
    ctx = RunManager(config).start(
        command=["main.py", "--", "--moises-api-key", secret, "--audio", "song.wav"],
        require_existing=False,
    )

    command_text = ctx.command_path.read_text(encoding="utf-8")
    manifest_text = ctx.manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    assert secret not in command_text
    assert secret not in manifest_text
    assert REDACTED_VALUE in command_text
    assert REDACTED_VALUE in manifest["command"]


def test_run_manager_redacts_cli_api_key_from_persisted_failures(tmp_path: Path) -> None:
    secret = "super-secret-key"
    config = RunConfig(output_root=tmp_path / "outputs")
    ctx = RunManager(config).start(
        command=["main.py", "--", "--moises-api-key", secret, "--audio", "song.wav"],
        require_existing=False,
    )

    ctx.record_warning(f"request warning included {secret}")
    ctx.record_error(f"request error included {secret}")
    ctx.finalize(success=False, error_summary=f"fatal request included {secret}")

    manifest_text = ctx.manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    assert secret not in manifest_text
    assert secret not in ctx.warnings[0]
    assert secret not in ctx.errors[0]
    assert secret not in (ctx.error_summary or "")
    assert REDACTED_VALUE in manifest["warnings"][0]
    assert REDACTED_VALUE in manifest["errors"][0]
    assert REDACTED_VALUE in manifest["error_summary"]
