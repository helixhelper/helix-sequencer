"""Frame renderer skeleton for Helix previews."""

from .timeline import PreviewTimeline


class PreviewRenderer:
    def __init__(self, timeline: PreviewTimeline, width: int = 1280, height: int = 720):
        self.timeline = timeline
        self.width = width
        self.height = height

    def render_frame(self, timestamp: float):
        """Render a frame from active timeline events.

        Pillow/moviepy integration will be added in the export milestone.
        """
        return {
            "timestamp": timestamp,
            "events": [e.action for e in self.timeline.active_at(timestamp)],
            "size": (self.width, self.height),
        }
