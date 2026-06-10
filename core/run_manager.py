"""Run lifecycle management for sequencer executions.

Tracks run state, artifacts, warnings, errors, and metadata throughout execution.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.run_config import RunConfig


@dataclass(frozen=True)
class RunArtifact:
    """Record of a captured artifact from a run."""

    kind: str
    path: str
    exists: bool


@dataclass
class RunContext:
    """Concrete paths and state for one Helix run."""

    config: RunConfig
    run_id: str
    run_dir: Path
    manifest_path: Path
    command_path: Path
    log_path: Path
    artifacts: list[RunArtifact] = field(default_factory=list)


class RunManager:
    """Manages the lifecycle of a sequencer run.

    Creates and maintains a timestamped run directory with command, log path,
    artifact records, and a manifest without mutating source inputs.
    """

    def __init__(self, config: RunConfig):
        self.config = config
        self.started_at = datetime.utcnow()
        self.finished_at: datetime | None = None
        self.run_id = f"{self.started_at.strftime('%Y%m%d-%H%M%S')}-{config.profile}"
        self.run_dir = config.output_root / "beta" / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.manifest_path = self.run_dir / "run_manifest.json"
        self.command_path = self.run_dir / "command.txt"
        self.log_path = self.run_dir / "helix.log"
        self.artifacts: list[RunArtifact] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.success: bool = False
        self.error_summary: Optional[str] = None

        self.context = RunContext(
            config=config,
            run_id=self.run_id,
            run_dir=self.run_dir,
            manifest_path=self.manifest_path,
            command_path=self.command_path,
            log_path=self.log_path,
            artifacts=self.artifacts,
        )

        self._write_command()
        self._write_manifest(status="started")

    def _command(self) -> list[str]:
        return [sys.argv[0], *self.config.to_engine_args()]

    def _git_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _path_value(self, path: Path | None) -> str | None:
        return str(path) if path is not None else None

    def _manifest_data(self, status: str) -> dict[str, Any]:
        return {
            "schema": "helix.run_manifest.v1",
            "app": "Helix Sequencer",
            "run_id": self.run_id,
            "profile": self.config.profile,
            "started_at": self.started_at.isoformat() + "Z",
            "finished_at": self.finished_at.isoformat() + "Z" if self.finished_at else None,
            "status": status,
            "audio_path": self._path_value(self.config.audio_path),
            "template_path": self._path_value(self.config.template_path),
            "layout_path": self._path_value(self.config.layout_path),
            "output_root": str(self.config.output_root),
            "run_dir": str(self.run_dir),
            "command": self._command(),
            "artifacts": [
                {"kind": artifact.kind, "path": artifact.path, "exists": artifact.exists}
                for artifact in self.artifacts
            ],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "success": self.success,
            "error_summary": self.error_summary,
            "git_commit": self._git_commit(),
        }

    def _write_command(self) -> None:
        try:
            self.command_path.write_text(" ".join(self._command()), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive logging only
            self.warnings.append(f"Failed to write command.txt: {exc}")

    def _write_manifest(self, status: str) -> None:
        try:
            self.manifest_path.write_text(
                json.dumps(self._manifest_data(status), indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # pragma: no cover - defensive logging only
            print(f"Warning: Failed to write run_manifest.json: {exc}", file=sys.stderr)

    def record_warning(self, warning: str) -> None:
        self.warnings.append(warning)
        self._write_manifest(status="started" if self.finished_at is None else "completed")

    def record_error(self, error: str) -> None:
        self.errors.append(error)
        self._write_manifest(status="started" if self.finished_at is None else "completed")

    def record_artifact(self, kind: str, path: Path | str) -> None:
        artifact_path = Path(path)
        artifact = RunArtifact(
            kind=kind,
            path=str(artifact_path),
            exists=artifact_path.exists(),
        )
        self.artifacts.append(artifact)
        self._write_manifest(status="started" if self.finished_at is None else "completed")

    def finalize(
        self,
        success: bool,
        error_summary: Optional[str] = None,
    ) -> None:
        self.finished_at = datetime.utcnow()
        self.success = success
        self.error_summary = error_summary
        if error_summary:
            self.errors.append(error_summary)
        self._write_manifest(status="completed")
