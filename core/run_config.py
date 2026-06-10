"""Configuration dataclass for sequencer runtime parameters.

Provides bidirectional conversion between CLI arguments and structured config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RunConfig:
    """Runtime configuration for the Helix sequencer engine.

    Supports conversion to/from CLI arguments via engine_args while preserving
    unknown arguments so the run spine can wrap the existing engine safely.
    """

    profile: str = "master"
    audio_path: Optional[Path] = None
    template_path: Optional[Path] = None
    layout_path: Optional[Path] = None
    output_root: Path = field(default_factory=lambda: Path("outputs"))
    variants: int = 1
    enable_orchestrator: bool = True
    promote_orchestrated_template: bool = True
    enable_learning_memory: bool = False
    power_metadata_path: Optional[Path] = None
    autosize_controllers: bool = False
    controller_padding: int = 50
    extra_engine_args: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_engine_args(cls, profile: str, engine_args: list[str]) -> "RunConfig":
        """Create RunConfig from existing engine CLI arguments.

        Known legacy spellings and the canonical issue #79 spellings are both
        accepted. Unknown flags are retained in ``extra_engine_args`` so visual
        output behavior is not changed by introducing the run spine.
        """
        config = cls(profile=profile)
        extra_args: list[str] = []

        value_flags = {
            "--audio": "audio_path",
            "--audio-path": "audio_path",
            "--audio_path": "audio_path",
            "--template": "template_path",
            "--template-path": "template_path",
            "--template_path": "template_path",
            "--layout": "layout_path",
            "--layout-file": "layout_path",
            "--layout-path": "layout_path",
            "--layout_path": "layout_path",
            "--output-dir": "output_root",
            "--output-root": "output_root",
            "--output_root": "output_root",
            "--power-metadata": "power_metadata_path",
            "--power-metadata-file": "power_metadata_path",
            "--power-metadata-path": "power_metadata_path",
            "--power_metadata_path": "power_metadata_path",
        }
        int_flags = {
            "--variants": "variants",
            "--controller-padding": "controller_padding",
            "--controller_padding": "controller_padding",
        }

        i = 0
        while i < len(engine_args):
            arg = engine_args[i]

            if arg in value_flags and i + 1 < len(engine_args):
                setattr(config, value_flags[arg], Path(engine_args[i + 1]))
                i += 2
            elif arg in int_flags and i + 1 < len(engine_args):
                try:
                    setattr(config, int_flags[arg], int(engine_args[i + 1]))
                except ValueError:
                    extra_args.extend([arg, engine_args[i + 1]])
                i += 2
            elif arg in {"--enable-orchestrator", "--enable_orchestrator"}:
                config.enable_orchestrator = True
                i += 1
            elif arg in {
                "--disable-orchestrator",
                "--disable_orchestrator",
                "--no-effects-orchestrator",
            }:
                config.enable_orchestrator = False
                i += 1
            elif arg in {"--promote-orchestrated-template", "--promote_orchestrated_template"}:
                config.promote_orchestrated_template = True
                i += 1
            elif arg in {
                "--no-promote-orchestrated-template",
                "--no_promote_orchestrated_template",
                "--no-orchestrator-template-promotion",
            }:
                config.promote_orchestrated_template = False
                i += 1
            elif arg in {
                "--enable-learning-memory",
                "--enable_learning_memory",
                "--learning-memory",
            }:
                config.enable_learning_memory = True
                i += 1
            elif arg in {
                "--disable-learning-memory",
                "--disable_learning_memory",
                "--no-learning-memory",
            }:
                config.enable_learning_memory = False
                i += 1
            elif arg in {"--autosize-controllers", "--autosize_controllers"}:
                config.autosize_controllers = True
                i += 1
            elif arg in {"--no-autosize-controllers", "--no_autosize_controllers"}:
                config.autosize_controllers = False
                i += 1
            else:
                extra_args.append(arg)
                i += 1

        config.extra_engine_args = tuple(extra_args)
        return config

    def to_engine_args(self) -> list[str]:
        """Convert RunConfig to canonical engine CLI arguments."""
        args: list[str] = []

        if self.audio_path is not None:
            args.extend(["--audio", str(self.audio_path)])
        if self.template_path is not None:
            args.extend(["--template", str(self.template_path)])
        if self.layout_path is not None:
            args.extend(["--layout-file", str(self.layout_path)])
        if self.output_root != Path("outputs"):
            args.extend(["--output-dir", str(self.output_root)])
        if self.variants != 1:
            args.extend(["--variants", str(self.variants)])

        if not self.enable_orchestrator:
            args.append("--no-effects-orchestrator")
        if not self.promote_orchestrated_template:
            args.append("--no-orchestrator-template-promotion")
        args.append("--learning-memory" if self.enable_learning_memory else "--no-learning-memory")

        if self.power_metadata_path is not None:
            args.extend(["--power-metadata-file", str(self.power_metadata_path)])
        if self.autosize_controllers:
            args.append("--autosize-controllers")
        if self.controller_padding != 50:
            args.extend(["--controller-padding", str(self.controller_padding)])

        args.extend(self.extra_engine_args)
        return args

    def validate_inputs(self, require_existing: bool = True) -> list[str]:
        """Return validation errors for configured input files and values."""
        errors: list[str] = []

        if self.variants < 1:
            errors.append("variants must be at least 1")
        if self.controller_padding < 0:
            errors.append("controller_padding must be non-negative")

        required_paths = (
            ("audio_path", self.audio_path),
            ("template_path", self.template_path),
            ("layout_path", self.layout_path),
        )
        optional_paths = (("power_metadata_path", self.power_metadata_path),)

        if require_existing:
            for field_name, path in required_paths:
                if path is None:
                    errors.append(f"{field_name} is required")
                elif not path.exists():
                    errors.append(f"{field_name} does not exist: {path}")
            for field_name, path in optional_paths:
                if path is not None and not path.exists():
                    errors.append(f"{field_name} does not exist: {path}")

        output_root = self.output_root.resolve(strict=False)
        for field_name, path in (*required_paths, *optional_paths):
            if path is None:
                continue
            source = path.resolve(strict=False)
            if output_root == source:
                errors.append(f"output_root must not be the same path as {field_name}: {path}")
            if output_root.parent == source.parent and output_root.name == source.name:
                errors.append(f"output_root would overwrite {field_name}: {path}")

        return errors
