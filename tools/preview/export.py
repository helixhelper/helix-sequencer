"""Preview frame export utilities."""

from pathlib import Path


class PreviewExporter:
    """Export rendered preview frames.

    Video backend intentionally isolated so moviepy/ffmpeg can be added
    without changing the renderer.
    """

    def __init__(self, output: str | Path):
        self.output = Path(output)

    def export_gif(self, frames: list, filename: str = "preview.gif") -> Path:
        path = self.output / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def export_mp4(self, frames: list, filename: str = "preview.mp4") -> Path:
        path = self.output / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
