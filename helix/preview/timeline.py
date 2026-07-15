"""Timeline primitives for preview playback."""

from dataclasses import dataclass, field
from typing import List


@dataclass(order=True)
class TimelineEvent:
    timestamp_ms: int
    name: str
    payload: dict = field(default_factory=dict, compare=False)


class Timeline:
    def __init__(self) -> None:
        self.events: List[TimelineEvent] = []

    def add(self, event: TimelineEvent) -> None:
        self.events.append(event)
        self.events.sort()

    def at(self, timestamp_ms: int) -> List[TimelineEvent]:
        return [e for e in self.events if e.timestamp_ms == timestamp_ms]
