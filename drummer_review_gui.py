from __future__ import annotations

import tkinter as tk
from typing import Any


DRUMMER_REVIEW_TYPES = ("kick", "snare", "hihat", "tom", "cymbal", "drum_bus")
DRUMMER_REVIEW_LABELS = {
    "kick": "Kick",
    "snare": "Snare",
    "hihat": "Hats",
    "tom": "Toms",
    "cymbal": "Cymbals",
    "drum_bus": "Fallback",
}
DRUMMER_REVIEW_COLORS = {
    "kick": "#d4785a",
    "snare": "#c4b48a",
    "hihat": "#7aada4",
    "tom": "#7a8eb0",
    "cymbal": "#b0a090",
    "drum_bus": "#8a7aa8",
}


class DrummerReviewWindow(tk.Toplevel):
    """Visual audit surface inspired by the supplied Drummer X studio."""

    BG = "#0a0a0b"
    SURFACE = "#121214"
    SURFACE_2 = "#1a1a1e"
    FG = "#f2f1ee"
    MUTED = "#9a9a96"
    SUBTLE = "#6e6e6a"
    BORDER = "#2b2b2f"

    def __init__(self, master: tk.Misc, summary: dict[str, Any]) -> None:
        super().__init__(master)
        self.summary = summary
        self.events = [dict(item) for item in list(summary.get("events", []) or [])]
        self.marker_positions: list[tuple[int, float, float]] = []
        self.selected_index: int | None = None
        self.detail_var = tk.StringVar(
            value="Click a timeline marker to inspect classification, confidence, and xLights placement."
        )
        self.title("Drummer X Review — Helix")
        self.geometry("1080x720")
        self.minsize(820, 620)
        self.configure(bg=self.BG)
        self._build()
        self.after_idle(self._redraw)

    def _build(self) -> None:
        header = tk.Frame(self, bg=self.BG)
        header.pack(fill=tk.X, padx=22, pady=(18, 10))
        tk.Label(
            header,
            text="DRUMMER X",
            bg=self.BG,
            fg=self.FG,
            font=("Segoe UI", 24, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text="HELIX V3 PERFORMANCE REVIEW",
            bg=self.BG,
            fg="#d4785a",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT, padx=16, pady=(10, 0))

        metrics = tk.Frame(self, bg=self.BG)
        metrics.pack(fill=tk.X, padx=18, pady=(0, 10))
        placed_cues = int(self.summary.get("placed_cues", 0) or 0)
        analyzed = int(self.summary.get("analyzed_cues", len(self.events)) or len(self.events))
        confidence = float(self.summary.get("average_confidence", 0.0) or 0.0)
        metric_rows = (
            ("Analyzed hits", str(analyzed)),
            ("Cues rendered", f"{placed_cues}/{analyzed}"),
            ("Average confidence", f"{confidence * 100:.0f}%"),
            ("Detection path", str(self.summary.get("fallback_mode", "unknown")).replace("_", " ")),
        )
        for index, (label, value) in enumerate(metric_rows):
            card = tk.Frame(metrics, bg=self.SURFACE_2, highlightbackground=self.BORDER, highlightthickness=1)
            card.grid(row=0, column=index, sticky="nsew", padx=4)
            metrics.columnconfigure(index, weight=1)
            tk.Label(card, text=label.upper(), bg=self.SURFACE_2, fg=self.SUBTLE, font=("Segoe UI", 8, "bold")).pack(
                anchor="w", padx=12, pady=(9, 1)
            )
            tk.Label(card, text=value, bg=self.SURFACE_2, fg=self.FG, font=("Segoe UI", 13, "bold")).pack(
                anchor="w", padx=12, pady=(0, 9)
            )

        kit_frame = tk.Frame(self, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        kit_frame.pack(fill=tk.BOTH, expand=True, padx=22, pady=6)
        self.kit_canvas = tk.Canvas(kit_frame, height=265, bg=self.SURFACE, highlightthickness=0)
        self.kit_canvas.pack(fill=tk.BOTH, expand=True)
        self.kit_canvas.bind("<Configure>", lambda _event: self._draw_kit())

        timeline_frame = tk.Frame(self, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        timeline_frame.pack(fill=tk.X, padx=22, pady=6)
        self.timeline_canvas = tk.Canvas(timeline_frame, height=202, bg=self.SURFACE, highlightthickness=0)
        self.timeline_canvas.pack(fill=tk.X)
        self.timeline_canvas.bind("<Configure>", lambda _event: self._draw_timeline())
        self.timeline_canvas.bind("<Button-1>", self._select_marker)

        footer = tk.Frame(self, bg=self.BG)
        footer.pack(fill=tk.X, padx=22, pady=(6, 16))
        tk.Label(
            footer,
            textvariable=self.detail_var,
            bg=self.BG,
            fg=self.MUTED,
            anchor="w",
            justify=tk.LEFT,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(
            footer,
            text="Close",
            command=self.destroy,
            bg=self.SURFACE_2,
            fg=self.FG,
            activebackground="#25252a",
            activeforeground=self.FG,
            relief=tk.FLAT,
            padx=16,
            pady=7,
        ).pack(side=tk.RIGHT)

    def _redraw(self) -> None:
        self._draw_kit()
        self._draw_timeline()

    def _draw_kit(self) -> None:
        canvas = self.kit_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        for row in range(1, 6):
            y = (height * row) / 6
            canvas.create_line(0, y, width, y, fill="#1d1d20")
        for column in range(1, 10):
            x = (width * column) / 10
            canvas.create_line(x, 0, x, height, fill="#1d1d20")

        counts = dict(self.summary.get("counts_by_type", {}) or {})
        total = max(1, sum(int(value or 0) for value in counts.values()))
        pieces = (
            ("Crash", "cymbal", 0.22, 0.24, 0.105, 0.035),
            ("Ride", "cymbal", 0.78, 0.25, 0.115, 0.038),
            ("Hats", "hihat", 0.16, 0.50, 0.085, 0.028),
            ("Tom L", "tom", 0.43, 0.38, 0.075, 0.047),
            ("Tom R", "tom", 0.59, 0.36, 0.078, 0.047),
            ("Snare", "snare", 0.33, 0.64, 0.088, 0.055),
            ("Kick", "kick", 0.53, 0.68, 0.16, 0.12),
        )
        for label, drum_type, x_frac, y_frac, rx_frac, ry_frac in pieces:
            x = width * x_frac
            y = height * y_frac
            rx = width * rx_frac
            ry = height * ry_frac
            count = int(counts.get(drum_type, 0) or 0)
            activity = min(1.0, count / max(1.0, total * 0.36))
            color = DRUMMER_REVIEW_COLORS[drum_type]
            canvas.create_oval(
                x - rx,
                y - ry,
                x + rx,
                y + ry,
                fill="#202024",
                outline=color,
                width=1 + int(round(activity * 4)),
            )
            canvas.create_text(x, y, text=str(count), fill=self.FG, font=("Segoe UI", 12, "bold"))
            canvas.create_text(x, y + ry + 13, text=label, fill=self.MUTED, font=("Segoe UI", 8))
        canvas.create_text(
            width - 14,
            13,
            anchor="ne",
            text=f"{self.summary.get('analysis_profile', 'unknown')} · marker size = velocity",
            fill=self.SUBTLE,
            font=("Segoe UI", 8),
        )

    def _draw_timeline(self) -> None:
        canvas = self.timeline_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        label_width = 82
        lane_height = height / len(DRUMMER_REVIEW_TYPES)
        duration_ms = max(
            1,
            int(self.summary.get("duration_ms", 0) or 0),
            max((int(event.get("end_ms", 0) or 0) for event in self.events), default=0),
        )
        for index, drum_type in enumerate(DRUMMER_REVIEW_TYPES):
            top = index * lane_height
            if index % 2 == 0:
                canvas.create_rectangle(0, top, width, top + lane_height, fill="#151518", outline="")
            canvas.create_text(
                10,
                top + lane_height / 2,
                anchor="w",
                text=DRUMMER_REVIEW_LABELS[drum_type],
                fill=DRUMMER_REVIEW_COLORS[drum_type],
                font=("Segoe UI", 8, "bold"),
            )
            canvas.create_line(label_width, top + lane_height, width, top + lane_height, fill="#2b2b2f")
        for index in range(11):
            x = label_width + ((width - label_width) * index / 10)
            canvas.create_line(x, 0, x, height, fill="#242428")
            if index < 10:
                canvas.create_text(
                    x + 3,
                    3,
                    anchor="nw",
                    text=f"{(duration_ms * index / 10000):.1f}s",
                    fill=self.SUBTLE,
                    font=("Segoe UI", 7),
                )

        self.marker_positions = []
        for event_index, event in enumerate(self.events):
            drum_type = str(event.get("drum_type", "drum_bus") or "drum_bus")
            if drum_type not in DRUMMER_REVIEW_TYPES:
                drum_type = "drum_bus"
            lane = DRUMMER_REVIEW_TYPES.index(drum_type)
            x = label_width + (width - label_width) * int(event.get("start_ms", 0) or 0) / duration_ms
            y = lane * lane_height + lane_height / 2
            velocity = max(0.0, min(1.0, float(event.get("velocity", 0.0) or 0.0)))
            radius = 2.5 + velocity * 4.0
            selected = event_index == self.selected_index
            placed = bool(event.get("placed", False))
            outline = self.FG if selected else ("#e46b68" if not placed else "")
            canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=DRUMMER_REVIEW_COLORS[drum_type],
                outline=outline,
                width=2 if outline else 0,
            )
            self.marker_positions.append((event_index, x, y))
        if not self.events:
            canvas.create_text(
                width / 2,
                height / 2,
                text="This report predates Drummer X event detail. Build a new sequence to populate the lanes.",
                fill=self.MUTED,
                font=("Segoe UI", 10),
            )

    def _select_marker(self, pointer: tk.Event[Any]) -> None:
        nearest: tuple[int, float] | None = None
        for event_index, x, y in self.marker_positions:
            distance = ((float(pointer.x) - x) ** 2 + (float(pointer.y) - y) ** 2) ** 0.5
            if distance <= 12 and (nearest is None or distance < nearest[1]):
                nearest = (event_index, distance)
        if nearest is None:
            return
        self.selected_index = nearest[0]
        event = self.events[self.selected_index]
        timestamp = int(event.get("start_ms", 0) or 0) / 1000.0
        confidence = float(event.get("confidence", 0.0) or 0.0) * 100
        velocity = float(event.get("velocity", 0.0) or 0.0)
        state = "placed" if bool(event.get("placed", False)) else "not placed"
        reasons = ", ".join(str(item) for item in list(event.get("placement_reasons", []) or []))
        reason_suffix = f" ({reasons})" if reasons else ""
        self.detail_var.set(
            f"{timestamp:.3f}s · {event.get('drum_type', 'hit')} · {event.get('pose', 'pose')} · "
            f"confidence {confidence:.0f}% · velocity {velocity:.2f} · {state}{reason_suffix} · "
            f"{event.get('source', 'unknown')}"
        )
        self._draw_timeline()



