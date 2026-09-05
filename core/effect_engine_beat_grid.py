from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable

from core.beat_grid_runtime import parse_beat_grid_runtime_args
from core import effect_engine
from core import self_improving_scoring
from core.controller_parser import build_controller_plan, write_networks_for_xsq_outputs
from core.run_config import RunConfig
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


def postprocess_beat_grid_outputs(
    root: Path,
    beat_grid,
    *,
    since: float | None = None,
    allowed_xsq_outputs: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Apply BeatGrid metadata/snapping to sidecars associated with this run's XSQs."""

    touched_reports = 0
    touched_snowman = 0
    scan_root = root.resolve()
    allowed_reports: set[Path] | None = None
    allowed_snowman: set[Path] | None = None
    if allowed_xsq_outputs is not None:
        outputs = list(allowed_xsq_outputs)
        allowed_reports = {
            path.with_name(f"{path.stem}.report.json").resolve(strict=False)
            for path in outputs
        }
        allowed_snowman = {
            path.with_name(f"{path.stem}.snowman_band.json").resolve(strict=False)
            for path in outputs
        }

    reports = list(scan_root.rglob(REPORT_GLOB))
    snowman_files = list(scan_root.rglob(SNOWMAN_GLOB))
    for path in reports:
        if allowed_reports is not None and path.resolve(strict=False) not in allowed_reports:
            continue
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
        if allowed_snowman is not None and path.resolve(strict=False) not in allowed_snowman:
            continue
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


def _artifact_search_roots(config: RunConfig, version: str) -> list[Path]:
    roots = [config.output_root]
    if config.output_root == Path("outputs"):
        family = version.split(".", 1)[0]
        if family:
            roots.append(Path(family))
    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(root)
    return unique


def _xsq_snapshot(roots: Iterable[Path]) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.xsq"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[path.resolve(strict=False)] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _changed_xsq_outputs(
    roots: Iterable[Path],
    before: dict[Path, tuple[int, int]],
) -> list[Path]:
    outputs: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.xsq"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            resolved = path.resolve(strict=False)
            if before.get(resolved) != (stat.st_mtime_ns, stat.st_size):
                outputs.append(path)
    return sorted(outputs, key=lambda path: str(path))


def _recent_xsq_outputs(roots: Iterable[Path], *, since: float) -> list[Path]:
    outputs: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.xsq"):
            if path.is_file() and _is_recent(path, since):
                outputs.append(path)
    return sorted(outputs, key=lambda path: str(path))


def _requested_audio_paths(argv: Iterable[str]) -> list[Path]:
    """Return audio paths explicitly supplied to the effect engine."""

    args = list(argv)
    requested: list[Path] = []
    idx = 0
    while idx < len(args):
        raw = args[idx]
        if raw == "--audio":
            idx += 1
            while idx < len(args) and not args[idx].startswith("--"):
                requested.append(Path(args[idx]))
                idx += 1
            continue
        if raw.startswith("--audio="):
            value = raw.split("=", 1)[1].strip()
            if value:
                requested.append(Path(value))
        idx += 1
    return requested


def _verify_requested_xsq_outputs(
    version: str,
    argv: list[str],
    *,
    before: dict[Path, tuple[int, int]],
) -> list[Path]:
    """Fail unless every explicitly requested song created or changed an XSQ."""

    requested = _requested_audio_paths(argv)
    if not requested:
        return []
    try:
        config = RunConfig.from_engine_args("engine", argv)
    except Exception as exc:
        raise RuntimeError(f"Unable to verify generated XSQ outputs: {exc}") from exc
    outputs = _changed_xsq_outputs(_artifact_search_roots(config, version), before)
    missing = [
        audio
        for audio in requested
        if not any(path.name.startswith(f"{audio.stem},{version}") for path in outputs)
    ]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise RuntimeError(
            "Effect engine returned without producing a fresh XSQ for requested audio: "
            f"{missing_text}"
        )
    return outputs


def _run_effect_engine_with_failure_capture(version: str, argv: list[str]) -> None:
    """Promote the legacy engine's swallowed per-song FAILED logs to an exception."""

    failures: list[str] = []
    original_log = effect_engine.log

    def capture_log(message: str) -> None:
        text = str(message)
        if text.lstrip().startswith("FAILED:"):
            failures.append(text.strip())
        original_log(message)

    effect_engine.log = capture_log
    try:
        effect_engine.main_for(version, argv)
    finally:
        effect_engine.log = original_log
    if failures:
        details = " | ".join(failures[:8])
        if len(failures) > 8:
            details += f" | ... and {len(failures) - 8} more"
        raise RuntimeError(f"Effect engine reported generation failure(s): {details}")


def _postprocess_beat_grid_for_run(
    version: str,
    argv: list[str],
    beat_grid,
    *,
    since: float,
    xsq_outputs: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Postprocess only sidecars belonging to this run's configured outputs."""

    try:
        config = RunConfig.from_engine_args("engine", argv)
    except Exception as exc:
        raise RuntimeError(f"Unable to scope BeatGrid postprocessing: {exc}") from exc
    outputs = list(xsq_outputs) if xsq_outputs is not None else None
    summaries = [
        postprocess_beat_grid_outputs(
            root,
            beat_grid,
            since=since,
            allowed_xsq_outputs=outputs,
        )
        for root in _artifact_search_roots(config, version)
    ]
    return {
        "enabled": True,
        "reports_touched": sum(int(item.get("reports_touched", 0)) for item in summaries),
        "snowman_exports_touched": sum(int(item.get("snowman_exports_touched", 0)) for item in summaries),
        "roots": [str(item.get("root", "")) for item in summaries],
        "subdivision": beat_grid.subdivision,
        "mode": beat_grid.mode,
    }


def autosize_controller_sidecars(
    version: str,
    argv: list[str],
    *,
    since: float,
    before: dict[Path, tuple[int, int]] | None = None,
) -> dict[str, Any] | None:
    """Copy or synthesize xlights_networks.xml beside XSQs changed by this run."""

    try:
        config = RunConfig.from_engine_args("engine", argv)
    except Exception as exc:
        raise RuntimeError(f"Unable to configure controller autosizing: {exc}") from exc
    if not config.autosize_controllers:
        return None
    if config.layout_path is None:
        raise RuntimeError("--autosize-controllers requires --layout-file")

    plan = build_controller_plan(config.layout_path, padding=config.controller_padding)
    roots = _artifact_search_roots(config, version)
    xsq_outputs = (
        _changed_xsq_outputs(roots, before)
        if before is not None
        else _recent_xsq_outputs(roots, since=since)
    )
    output_targets = xsq_outputs or [config.output_root]
    sidecars = write_networks_for_xsq_outputs(plan, output_targets)
    return {
        "enabled": True,
        "source": plan.source,
        "channel_count": plan.channel_count,
        "layout_channel_count": plan.layout_channel_count,
        "synthesized_null_controller": plan.synthesized_null_controller,
        "xsq_outputs": [str(path) for path in xsq_outputs],
        "sidecars": [str(path) for path in sidecars],
    }


def main_for(version: str, argv: list[str] | None = None) -> None:
    """Run effect_engine while consuming BeatGrid runtime flags."""

    started = time.time()
    options = parse_beat_grid_runtime_args(argv or [])
    cleaned_args = list(options.cleaned_args)
    try:
        config = RunConfig.from_engine_args("engine", cleaned_args)
    except Exception as exc:
        raise RuntimeError(f"Unable to snapshot generated XSQ outputs: {exc}") from exc
    roots = _artifact_search_roots(config, version)
    before_xsq = _xsq_snapshot(roots)

    _run_effect_engine_with_failure_capture(version, cleaned_args)
    changed_xsq = _changed_xsq_outputs(roots, before_xsq)
    _verify_requested_xsq_outputs(version, cleaned_args, before=before_xsq)
    controller_summary = autosize_controller_sidecars(
        version,
        cleaned_args,
        since=started,
        before=before_xsq,
    )
    if controller_summary is not None:
        effect_engine.log(
            "Controller autosize: "
            f"source={controller_summary['source']} channels={controller_summary['channel_count']} "
            f"sidecars={len(controller_summary['sidecars'])}"
        )
    if options.snap_timing and options.beat_grid is not None:
        summary = _postprocess_beat_grid_for_run(
            version,
            cleaned_args,
            options.beat_grid,
            since=started,
            xsq_outputs=changed_xsq,
        )
        effect_engine.log(
            "BeatGrid postprocess: "
            f"reports={summary['reports_touched']} snowman={summary['snowman_exports_touched']} "
            f"grid={summary['subdivision']} mode={summary['mode']}"
        )


def main(argv: list[str] | None = None) -> None:
    main_for(effect_engine.ACTIVE_STYLE_VERSION, argv)


if __name__ == "__main__":
    main()
