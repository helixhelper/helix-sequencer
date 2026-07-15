"""Low-resource preview canvas primitives.

Designed for machines that cannot run full xLights preview rendering.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Canvas:
    width: int = 800
    height: int = 450
    pixels: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def clear(self) -> None:
        self.pixels.clear()

    def draw_model(self, name: str, channels: Dict[str, float]) -> None:
        self.pixels[name] = dict(channels)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        return dict(self.pixels)
