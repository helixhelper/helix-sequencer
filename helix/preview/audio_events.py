"""Audio event adapters used by preview playback."""

from dataclasses import dataclass


@dataclass
class AudioEvent:
    timestamp_ms: int
    kind: str
    intensity: float = 1.0


def from_beat(timestamp_ms: int, intensity: float = 1.0) -> AudioEvent:
    """Create a preview event from a detected beat."""
    return AudioEvent(timestamp_ms, "beat", intensity)
