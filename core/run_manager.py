"""Run lifecycle management for sequencer executions.

Tracks run state, artifacts, and metadata throughout execution.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.run_config import RunConfig


@dataclass
class ArtifactRecord:
    """Record of a captured artifact from a run."""

    kind: str
    path: str
    recorded_at: str


class RunManager:
    """Manages the lifecycle of a sequencer run.

    Creates and maintains a timestamped run directory with manifest and metadata.
    """

    def __init__(self, config: RunConfig):
        """Initialize RunManager with a config and set up run directory.

        Args:
            config: RunConfig instance defining output location and parameters.

        Creates:
            - Timestamped run directory under config.output_root
            - command.txt with invocation command
            - run_manifest.json with initial metadata
        """
        self.config = config
        self.started_at = datetime.utcnow()
        self.run_id = self.started_at.strftime("%Y%m%d_%H%M%S_%f")[:-3]

        # Create run directory
        self.run_dir = config.output_root / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Write command.txt
        self._write_command()

        # Initialize manifest
        self.artifacts: list[ArtifactRecord] = []
        self.manifest_path = self.run_dir / "run_manifest.json"
        self._write_manifest()

    def _write_command(self) -> None:
        """Write command.txt with the invocation command."""
        command_file = self.run_dir / "command.txt"
        engine_args = self.config.to_engine_args()
        command_line = " ".join([sys.argv[0]] + engine_args)

        try:
            command_file.write_text(command_line, encoding="utf-8")
        except Exception as e:
            print(f"Warning: Failed to write command.txt: {e}", file=sys.stderr)

    def _write_manifest(self) -> None:
        """Write or update run_manifest.json."""
        manifest_data: dict[str, Any] = {
            "schema": "helix.run_manifest.v1",
            "status": "started",
            "run_id": self.run_id,
            "profile": self.config.profile,
            "started_at": self.started_at.isoformat() + "Z",
            "finished_at": None,
            "success": None,
            "artifacts": [
                {
                    "kind": artifact.kind,
                    "path": artifact.path,
                    "recorded_at": artifact.recorded_at,
                }
                for artifact in self.artifacts
            ],
            "errors": [],
        }

        try:
            self.manifest_path.write_text(
                json.dumps(manifest_data, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"Warning: Failed to write run_manifest.json: {e}", file=sys.stderr)

    def record_artifact(self, kind: str, path: Path) -> None:
        """Record an artifact produced during the run.

        Args:
            kind: Type/category of artifact (e.g., "effect_placement", "debug_log").
            path: Path to the artifact file.

        Updates run_manifest.json with the new artifact record.
        """
        if not isinstance(path, Path):
            path = Path(path)

        recorded_at = datetime.utcnow().isoformat() + "Z"
        artifact = ArtifactRecord(
            kind=kind,
            path=str(path),
            recorded_at=recorded_at,
        )
        self.artifacts.append(artifact)
        self._write_manifest()

    def finalize(
        self,
        success: bool,
        error_summary: Optional[str] = None,
    ) -> None:
        """Finalize the run and close the manifest.

        Args:
            success: Whether the run completed successfully.
            error_summary: Optional error message or summary.

        Updates run_manifest.json with:
            - status: "completed"
            - success: bool result
            - finished_at: completion timestamp
            - errors: error details if any
        """
        finished_at = datetime.utcnow()

        manifest_data: dict[str, Any] = {
            "schema": "helix.run_manifest.v1",
            "status": "completed",
            "run_id": self.run_id,
            "profile": self.config.profile,
            "started_at": self.started_at.isoformat() + "Z",
            "finished_at": finished_at.isoformat() + "Z",
            "success": success,
            "artifacts": [
                {
                    "kind": artifact.kind,
                    "path": artifact.path,
                    "recorded_at": artifact.recorded_at,
                }
                for artifact in self.artifacts
            ],
            "errors": [error_summary] if error_summary else [],
        }

        try:
            self.manifest_path.write_text(
                json.dumps(manifest_data, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"Warning: Failed to finalize run_manifest.json: {e}", file=sys.stderr)
