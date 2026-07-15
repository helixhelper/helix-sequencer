"""Preview export interfaces."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .renderer import Frame


@dataclass
class ExportResult:
    path: Path
    frame_count: int


class PreviewExporter:
    """Minimal exporter contract.

    Actual video encoding is intentionally isolated so ffmpeg/image backends
    can be added without changing sequencing logic.
    """

    def export_frames(self, frames: Iterable[Frame], output: Path) -> ExportResult:
        frames = list(frames)
        output.write_text(f"Helix preview frames: {len(frames)}\n")
        return ExportResult(output, len(frames))
