from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunConfig:
    profile: str = "master"
    audio_path: Path | None = None
    template_path: Path | None = None
    layout_path: Path | None = None
    output_root: Path = Path("outputs")
    variants: int = 1
    enable_orchestrator: bool = True
    promote_orchestrated_template: bool = True
    enable_learning_memory: bool = False
    power_metadata_path: Path | None = None
    autosize_controllers: bool = False
    controller_padding: int = 50
    extra_engine_args: tuple[str, ...] = ()

    @classmethod
    def from_engine_args(cls, profile: str, engine_args: list[str]) -> "RunConfig":
        audio_path: Path | None = None
        template_path: Path | None = None
        layout_path: Path | None = None
        output_root = Path("outputs")
        variants = 1
        enable_orchestrator = True
        promote_orchestrated_template = True
        enable_learning_memory = False
        power_metadata_path: Path | None = None
        autosize_controllers = False
        controller_padding = 50
        extra: list[str] = []

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

        args = list(engine_args)
        index = 0
        while index < len(args):
            arg = args[index]
            consumed = 1

            def value_after(flag: str) -> str | None:
                if arg.startswith(f"{flag}="):
                    return arg.split("=", 1)[1]
                if arg == flag and index + 1 < len(args):
                    return args[index + 1]
                return None

            matched = False
            for flag, field_name in value_flags.items():
                value = value_after(flag)
                if value is None:
                    continue
                if field_name == "audio_path":
                    audio_path = Path(value) if value else None
                elif field_name == "template_path":
                    template_path = Path(value) if value else None
                elif field_name == "layout_path":
                    layout_path = Path(value) if value else None
                elif field_name == "output_root":
                    output_root = Path(value)
                elif field_name == "power_metadata_path":
                    power_metadata_path = Path(value) if value else None
                consumed = 1 if arg.startswith(f"{flag}=") else 2
                matched = True
                break
            if matched:
                index += consumed
                continue

            for flag, field_name in int_flags.items():
                value = value_after(flag)
                if value is None:
                    continue
                try:
                    parsed = int(value)
                except ValueError:
                    parsed = 0 if field_name == "variants" else -1
                if field_name == "variants":
                    variants = parsed
                elif field_name == "controller_padding":
                    controller_padding = parsed
                consumed = 1 if arg.startswith(f"{flag}=") else 2
                matched = True
                break
            if matched:
                index += consumed
                continue

            if arg in {"--enable-orchestrator", "--enable_orchestrator"}:
                enable_orchestrator = True
            elif arg in {"--disable-orchestrator", "--disable_orchestrator", "--no-effects-orchestrator"}:
                enable_orchestrator = False
            elif arg in {"--promote-orchestrated-template", "--promote_orchestrated_template"}:
                promote_orchestrated_template = True
            elif arg in {
                "--no-promote-orchestrated-template",
                "--no_promote_orchestrated_template",
                "--no-orchestrator-template-promotion",
            }:
                promote_orchestrated_template = False
            elif arg in {"--enable-learning-memory", "--enable_learning_memory", "--learning-memory"}:
                enable_learning_memory = True
            elif arg in {"--disable-learning-memory", "--disable_learning_memory", "--no-learning-memory"}:
                enable_learning_memory = False
            elif arg in {"--autosize-controllers", "--autosize_controllers"}:
                autosize_controllers = True
            elif arg in {"--no-autosize-controllers", "--no_autosize_controllers"}:
                autosize_controllers = False
            else:
                extra.append(arg)

            index += consumed

        return cls(
            profile=profile,
            audio_path=audio_path,
            template_path=template_path,
            layout_path=layout_path,
            output_root=output_root,
            variants=variants,
            enable_orchestrator=enable_orchestrator,
            promote_orchestrated_template=promote_orchestrated_template,
            enable_learning_memory=enable_learning_memory,
            power_metadata_path=power_metadata_path,
            autosize_controllers=autosize_controllers,
            controller_padding=controller_padding,
            extra_engine_args=tuple(extra),
        )

    def to_engine_args(self) -> list[str]:
        args: list[str] = []
        if self.template_path is not None:
            args.extend(["--template", str(self.template_path)])
        if self.audio_path is not None:
            args.extend(["--audio", str(self.audio_path)])
        if self.layout_path is not None:
            args.extend(["--layout-file", str(self.layout_path)])
        if self.output_root != Path("outputs"):
            args.extend(["--output-dir", str(self.output_root)])
        args.extend(["--variants", str(self.variants)])
        args.append("--learning-memory" if self.enable_learning_memory else "--no-learning-memory")
        if self.power_metadata_path is not None:
            args.extend(["--power-metadata-file", str(self.power_metadata_path)])
        if self.autosize_controllers:
            args.append("--autosize-controllers")
        args.extend(["--controller-padding", str(self.controller_padding)])
        if not self.enable_orchestrator:
            args.append("--no-effects-orchestrator")
        if not self.promote_orchestrated_template:
            args.append("--no-orchestrator-template-promotion")
        args.extend(self.extra_engine_args)
        return args

    def validate_inputs(self, require_existing: bool = True) -> list[str]:
        errors: list[str] = []
        output_root = _safe_resolve(self.output_root)

        if self.variants < 1:
            errors.append(f"variants must be at least 1: {self.variants}")
        if self.controller_padding < 0:
            errors.append(f"controller_padding must be non-negative: {self.controller_padding}")

        for label, source in (
            ("audio", self.audio_path),
            ("template", self.template_path),
            ("layout", self.layout_path),
        ):
            if source is None:
                if require_existing:
                    errors.append(f"{label} path is required")
                continue
            errors.extend(_validate_source_path(label, source, output_root, require_existing))

        if self.power_metadata_path is not None and require_existing and not self.power_metadata_path.exists():
            errors.append(f"power metadata path does not exist: {self.power_metadata_path}")

        return errors


def _validate_source_path(label: str, source: Path, output_root: Path, require_existing: bool) -> list[str]:
    errors: list[str] = []
    source_path = _safe_resolve(source)

    if require_existing:
        if not source.exists():
            errors.append(f"{label} path does not exist: {source}")
        elif not source.is_file():
            errors.append(f"{label} path is not a file: {source}")
        elif not _is_readable(source):
            errors.append(f"{label} path is not readable: {source}")

    if output_root == source_path:
        errors.append(f"output_root must not equal {label} path: {source}")
    if output_root == source_path.parent:
        errors.append(f"output_root must not be the {label} source folder: {source_path.parent}")
    if _is_relative_to(output_root, source_path):
        errors.append(f"output_root must not be inside the {label} file path: {source}")

    return errors


def _safe_resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_readable(path: Path) -> bool:
    try:
        with path.open("rb"):
            return True
    except OSError:
        return False
