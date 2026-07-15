"""Event timeline primitives for Helix preview rendering."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class PreviewEvent:
    """A synchronized animation event."""

    time: float
    action: str
    payload: dict[str, Any] = field(default_factory=dict, compare=False)


class PreviewTimeline:
    """Stores and queries ordered preview events."""

    def __init__(self) -> None:
        self.events: list[PreviewEvent] = []

    def add(self, event: PreviewEvent) -> None:
        self.events.append(event)
        self.events.sort()

    def active_at(self, timestamp: float) -> list[PreviewEvent]:
        return [e for e in self.events if e.time <= timestamp]
