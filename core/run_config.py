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
    
    Supports conversion to/from CLI arguments via engine_args.
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
    def from_engine_args(cls, profile: str, engine_args: list[str]) -> RunConfig:
        """Create RunConfig from CLI arguments.
        
        Args:
            profile: The profile name (e.g. "master").
            engine_args: List of CLI arguments to parse.
        
        Returns:
            RunConfig instance with parsed arguments.
        """
        config = cls(profile=profile)
        extra_args: list[str] = []
        
        i = 0
        while i < len(engine_args):
            arg = engine_args[i]
            
            if arg == "--audio_path" and i + 1 < len(engine_args):
                config.audio_path = Path(engine_args[i + 1])
                i += 2
            elif arg == "--template_path" and i + 1 < len(engine_args):
                config.template_path = Path(engine_args[i + 1])
                i += 2
            elif arg == "--layout_path" and i + 1 < len(engine_args):
                config.layout_path = Path(engine_args[i + 1])
                i += 2
            elif arg == "--output_root" and i + 1 < len(engine_args):
                config.output_root = Path(engine_args[i + 1])
                i += 2
            elif arg == "--variants" and i + 1 < len(engine_args):
                try:
                    config.variants = int(engine_args[i + 1])
                except ValueError:
                    extra_args.extend([arg, engine_args[i + 1]])
                i += 2
            elif arg == "--enable_orchestrator":
                config.enable_orchestrator = True
                i += 1
            elif arg == "--disable_orchestrator":
                config.enable_orchestrator = False
                i += 1
            elif arg == "--promote_orchestrated_template":
                config.promote_orchestrated_template = True
                i += 1
            elif arg == "--no_promote_orchestrated_template":
                config.promote_orchestrated_template = False
                i += 1
            elif arg == "--enable_learning_memory":
                config.enable_learning_memory = True
                i += 1
            elif arg == "--disable_learning_memory":
                config.enable_learning_memory = False
                i += 1
            elif arg == "--power_metadata_path" and i + 1 < len(engine_args):
                config.power_metadata_path = Path(engine_args[i + 1])
                i += 2
            elif arg == "--autosize_controllers":
                config.autosize_controllers = True
                i += 1
            elif arg == "--no_autosize_controllers":
                config.autosize_controllers = False
                i += 1
            elif arg == "--controller_padding" and i + 1 < len(engine_args):
                try:
                    config.controller_padding = int(engine_args[i + 1])
                except ValueError:
                    extra_args.extend([arg, engine_args[i + 1]])
                i += 2
            else:
                extra_args.append(arg)
                i += 1
        
        config.extra_engine_args = tuple(extra_args)
        return config

    def to_engine_args(self) -> list[str]:
        """Convert RunConfig to CLI arguments.
        
        Returns:
            List of CLI arguments ready for engine invocation.
        """
        args: list[str] = []
        
        if self.audio_path is not None:
            args.extend(["--audio_path", str(self.audio_path)])
        
        if self.template_path is not None:
            args.extend(["--template_path", str(self.template_path)])
        
        if self.layout_path is not None:
            args.extend(["--layout_path", str(self.layout_path)])
        
        if self.output_root != Path("outputs"):
            args.extend(["--output_root", str(self.output_root)])
        
        if self.variants != 1:
            args.extend(["--variants", str(self.variants)])
        
        if self.enable_orchestrator:
            args.append("--enable_orchestrator")
        else:
            args.append("--disable_orchestrator")
        
        if self.promote_orchestrated_template:
            args.append("--promote_orchestrated_template")
        else:
            args.append("--no_promote_orchestrated_template")
        
        if self.enable_learning_memory:
            args.append("--enable_learning_memory")
        else:
            args.append("--disable_learning_memory")
        
        if self.power_metadata_path is not None:
            args.extend(["--power_metadata_path", str(self.power_metadata_path)])
        
        if self.autosize_controllers:
            args.append("--autosize_controllers")
        else:
            args.append("--no_autosize_controllers")
        
        if self.controller_padding != 50:
            args.extend(["--controller_padding", str(self.controller_padding)])
        
        args.extend(self.extra_engine_args)
        
        return args
