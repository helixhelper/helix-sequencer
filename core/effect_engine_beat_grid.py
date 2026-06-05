from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable

from core.beat_grid_runtime import parse_beat_grid_runtime_args
from core import effect_engine
from core import self_improving_scoring
from core.snowman_band_beat_grid import snap_snowman_band_payload_to_grid


REPORT_GLOB = "*.report.json"
SNOWMAN_GLOB = "*.snowman_band.json"


def _json_read(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _json_write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _is_recent(path: Path, since: float) -> bool:
    try:
        return path.stat().st_mtime >= since - 1.0
    except OSError:
        return False


def _is_helix_report(payload: dict[str, Any]) -> bool:
    return self_improving_scoring.is_helix_generated_payload(payload)


def _apply_to_report_payload(payload: dict[str, Any], beat_grid) -> dict[str, Any]:
    snowman = payload.get("snowman_band")
    if isinstance(snowman, dict):
        payload["snowman_band"] = snap_snowman_band_payload_to_grid(snowman, beat_grid)
    for key in ("global_timeline", "timing_intelligence", "xlights_translation"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            wrapper = {key: nested}
            snap_snowman_band_payload_to_grid(wrapper, beat_grid)
            payload[key] = wrapper[key]
    payload.setdefault("beat_grid", {})
    if isinstance(payload["beat_grid"], dict):
        payload["beat_grid"].update(
            {
                "snapped": True,
                "subdivision": beat_grid.subdivision,
                "bpm": beat_grid.bpm,
                "offset_ms": beat_grid.offset_ms,
                "mode": beat_grid.mode,
                "max_shift_ms": beat_grid.max_shift_ms,
                "source": "effect_engine_beat_grid_wrapper",
            }
        )
    payload["self_improving_scoring"] = self_improving_scoring.score_sequence(payload).as_dict()
    return payload


def postprocess_beat_grid_outputs(root: Path, beat_grid, *, since: float | None = None) -> dict[str, Any]:
    """Apply BeatGrid metadata/snapping to freshly generated report sidecars."""

    touched_reports = 0
    touched_snowman = 0
    scan_root = root.resolve()
    reports = list(scan_root.rglob(REPORT_GLOB))
    snowman_files = list(scan_root.rglob(SNOWMAN_GLOB))
    for path in reports:
        if since is not None and not _is_recent(path, since):
            continue
        payload = _json_read(path)
        if not payload or not _is_helix_report(payload):
            continue
        if ((payload.get("beat_grid") or {}) or {}).get("snapped"):
            continue
        _json_write(path, _apply_to_report_payload(payload, beat_grid))
        touched_reports += 1
    for path in snowman_files:
        if since is not None and not _is_recent(path, since):
            continue
        payload = _json_read(path)
        if not payload:
            continue
        if ((payload.get("beat_grid") or {}) or {}).get("snapped"):
            continue
        _json_write(path, snap_snowman_band_payload_to_grid(payload, beat_grid))
        touched_snowman += 1
    return {
        "enabled": True,
        "reports_touched": touched_reports,
        "snowman_exports_touched": touched_snowman,
        "root": str(scan_root),
        "subdivision": beat_grid.subdivision,
        "mode": beat_grid.mode,
    }


def main_for(version: str, argv: list[str] | None = None) -> None:
    """Run effect_engine while consuming BeatGrid runtime flags.

    This keeps the existing effect_engine stable: unknown BeatGrid flags are
    stripped before the legacy parser sees them, and generated report sidecars
    are upgraded with raw/snapped timing metadata afterward.
    """

    started = time.time()
    options = parse_beat_grid_runtime_args(argv or [])
    effect_engine.main_for(version, list(options.cleaned_args))
    if options.snap_timing and options.beat_grid is not None:
        summary = postprocess_beat_grid_outputs(Path("."), options.beat_grid, since=started)
        effect_engine.log(
            "BeatGrid postprocess: "
            f"reports={summary['reports_touched']} snowman={summary['snowman_exports_touched']} "
            f"grid={summary['subdivision']} mode={summary['mode']}"
        )


def main(argv: list[str] | None = None) -> None:
    effect_engine.main_for(effect_engine.ACTIVE_STYLE_VERSION, argv)


if __name__ == "__main__":
    main()
