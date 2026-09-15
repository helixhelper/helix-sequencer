from __future__ import annotations

import json
from pathlib import Path

from gui_launcher import (
    BetaRunOptions,
    QueueWriter,
    build_engine_argv,
    inspect_drummer_layout,
    latest_drummer_summary,
)


def test_beta_gui_builds_in_process_engine_arguments(tmp_path: Path) -> None:
    options = BetaRunOptions(
        profile="master",
        template=tmp_path / "template.xsq",
        audio=tmp_path / "song.wav",
        layout=tmp_path / "xlights_rgbeffects.xml",
        output_dir=tmp_path / "outputs",
        variants=3,
    )

    args = build_engine_argv(options)

    assert args[:3] == ["--profile", "master", "--"]
    assert "--template" in args
    assert "--audio" in args
    assert "--layout-file" in args
    assert "--learning-memory" in args
    assert "--matrix-intelligence" in args
    assert "--polish" in args
    assert "--auto-shortlist" in args
    assert "--no-birdsong" in args
    assert "--sync-lyrics-heads" not in args
    assert "main.py" not in args


def test_beta_gui_can_enable_optional_overlays(tmp_path: Path) -> None:
    options = BetaRunOptions(
        profile="master",
        template=tmp_path / "template.xsq",
        audio=tmp_path / "song.wav",
        layout=tmp_path / "layout.xml",
        output_dir=tmp_path / "outputs",
        birdsong=True,
        sync_lyrics=True,
        vendor_bar=True,
    )

    args = build_engine_argv(options)

    assert "--birdsong" in args
    assert "--birdsong-auto" in args
    assert "--sync-lyrics-heads" in args
    assert "--vendor-bar" in args


def test_layout_inspection_reports_missing_and_ready_drummer(tmp_path: Path) -> None:
    missing = inspect_drummer_layout(tmp_path / "missing.xml")
    assert not missing["ready"]
    assert missing["state"] == "layout_missing"

    poses = "\n".join(
        f'<subModel name="HX_SNOWMAN_DRUMMER_HIT_POSE_{index}" line0="{index + 1}" />'
        for index in range(8)
    )
    layout = tmp_path / "layout.xml"
    layout.write_text(
        (
            "<xrgb><models>"
            '<model name="HX_SNOWMAN_DRUMMER" CustomModel="1" '
            'HelixImplementationState="drummer_v3_beta" HelixNodeCount="42">'
            f"{poses}</model></models></xrgb>"
        ),
        encoding="utf-8",
    )

    ready = inspect_drummer_layout(layout)
    assert ready["ready"]
    assert ready["pose_count"] == 8
    assert ready["state"] == "drummer_v3_beta"


def test_latest_drummer_summary_reads_render_counts(tmp_path: Path) -> None:
    report = tmp_path / "song.report.json"
    report.write_text(
        json.dumps(
            {
                "drummer": {
                    "fallback_mode": "typed_detection",
                    "analyzed_cues": 12,
                    "placement_requests": 12,
                    "placed_effects": 10,
                    "timing_track_events": 10,
                    "review": {
                        "analysis_profile": "drummer_x_hybrid",
                        "average_confidence": 0.78,
                        "counts_by_type": {"kick": 3, "snare": 4},
                        "events": [
                            {
                                "start_ms": 100,
                                "end_ms": 240,
                                "drum_type": "kick",
                                "velocity": 0.9,
                                "confidence": 0.82,
                                "placed": True,
                            }
                        ],
                        "placed_cues": 10,
                        "unplaced_cues": 2,
                        "cue_placement_ratio": 0.833,
                        "duration_ms": 4000,
                    },
                },
                "quality": {"score": 91.4, "grade": "A"},
            }
        ),
        encoding="utf-8",
    )

    summary = latest_drummer_summary(tmp_path)

    assert summary is not None
    assert summary["fallback_mode"] == "typed_detection"
    assert summary["placed_effects"] == 10
    assert summary["quality_grade"] == "A"
    assert summary["analysis_profile"] == "drummer_x_hybrid"
    assert summary["average_confidence"] == 0.78
    assert summary["counts_by_type"]["kick"] == 3
    assert summary["events"][0]["placed"] is True


def test_queue_writer_emits_complete_and_partial_lines() -> None:
    events: list[tuple[str, object]] = []
    writer = QueueWriter(events.append)

    writer.write("first\nsec")
    writer.write("ond\nthird")
    writer.flush()

    assert events == [
        ("log", "first"),
        ("log", "second"),
        ("log", "third"),
    ]
