"""Helix lightweight preview simulation package.

Provides timeline-driven preview rendering helpers without requiring xLights.
"""

from .renderer import FrameRenderer
from .timeline import Timeline, TimelineEvent

__all__ = ["FrameRenderer", "Timeline", "TimelineEvent"]
