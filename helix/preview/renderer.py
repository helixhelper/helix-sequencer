"""Simple layout-agnostic preview frame renderer."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Frame:
    """A single preview frame of model brightness values."""

    timestamp_ms: int
    models: Dict[str, Dict[str, float]] = field(default_factory=dict)


class PreviewRenderer:
    """Convert timeline state into preview frames.

    This intentionally stays independent from xLights and controllers. The
    output can later feed a GUI canvas, video renderer, or diagnostics view.
    """

    def render(self, timestamp_ms: int, state: Dict[str, Dict[str, float]]) -> Frame:
        return Frame(timestamp_ms=timestamp_ms, models=state.copy())
