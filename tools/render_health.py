#!/usr/bin/env python3
"""Validate final show/render evidence independently from Helix's internal quality score.

This module intentionally scores observable output health rather than musical or
artistic intent.  It combines the finalized show manifest with the rendered
preview density sidecar so a structurally impressive report cannot hide a black,
tiny, timing-only, recovery-only, or poorly distributed result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MIN_ROOT_PARTICIPATION_RATIO = 0.15
MIN_MEAN_BRIGHT_PIXEL_RATIO = 0.002
MIN_MAX_SPREAD_RATIO = 0.25
MIN_DENSITY_SAMPLES = 3
MIN_DRUMMER_PLACEMENT_RATIO = 0.95
REQUIRED_DRUM_TYPES = ("kick", "snare", "hihat", "tom", "cymbal")


class RenderHealthError(RuntimeError):
    """Raised when render-health inputs are missing or malformed."""


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RenderHealthError(f"Cannot read render-health JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RenderHealthError(f"Render-health JSON is not an object: {path}")
    return payload


def evaluate_render_health(
    show: dict[str, Any],
    density: dict[str, Any],
    *,
    require_drummer: bool = False,
    require_native_choreography: bool = False,
) -> dict[str, Any]:
    """Return a fail-closed health assessment from finalized/rendered evidence."""

    issues: list[str] = []
    model_effects = _positive_int(show.get("model_effects"))
    models_with_effects = _positive_int(show.get("models_with_effects"))
    root_participation = _number(show.get("root_model_participation_ratio"))
    recovery_effects = _positive_int(show.get("general_effects_added"))
    channel_overlaps = _positive_int(show.get("channel_overlap_count"))

    sample_count = _positive_int(density.get("sample_count"))
    mean_bright = _number(density.get("mean_bright_pixel_ratio"))
    max_spread = _number(density.get("max_spread_ratio"))

    if model_effects <= 0:
        issues.append("final XSQ has no model effects")
    if models_with_effects <= 0:
        issues.append("final XSQ has no active model rows")
    if root_participation < MIN_ROOT_PARTICIPATION_RATIO:
        issues.append(
            "root-model participation is too low "
            f"({root_participation:.3f} < {MIN_ROOT_PARTICIPATION_RATIO:.3f})"
        )
    if channel_overlaps:
        issues.append(f"layout has {channel_overlaps} channel overlap(s)")
    if require_native_choreography and recovery_effects:
        issues.append(
            "golden preview relied on beta recovery choreography "
            f"({recovery_effects} recovery effect(s))"
        )

    if sample_count < MIN_DENSITY_SAMPLES:
        issues.append(
            f"visual-density evidence has too few samples ({sample_count} < {MIN_DENSITY_SAMPLES})"
        )
    if mean_bright < MIN_MEAN_BRIGHT_PIXEL_RATIO:
        issues.append(
            "render is too dark/sparse "
            f"(mean bright-pixel ratio {mean_bright:.5f} < {MIN_MEAN_BRIGHT_PIXEL_RATIO:.5f})"
        )
    if max_spread < MIN_MAX_SPREAD_RATIO:
        issues.append(
            "render activity is too spatially concentrated "
            f"(max spread ratio {max_spread:.3f} < {MIN_MAX_SPREAD_RATIO:.3f})"
        )

    drummer = show.get("drummer", {})
    if not isinstance(drummer, dict):
        drummer = {}
    drummer_requests = _positive_int(drummer.get("timing_events"))
    drummer_placed = _positive_int(drummer.get("placed_effects"))
    drummer_ratio = (
        min(1.0, drummer_placed / drummer_requests)
        if drummer_requests > 0
        else 0.0
    )
    placed_by_type = drummer.get("placed_by_type", {})
    if not isinstance(placed_by_type, dict):
        placed_by_type = {}
    normalized_types = {
        str(key).strip().lower(): _positive_int(value)
        for key, value in placed_by_type.items()
    }

    if require_drummer:
        if drummer_requests <= 0:
            issues.append("Drummer V3 has no timing/placement requests")
        if drummer_ratio < MIN_DRUMMER_PLACEMENT_RATIO:
            issues.append(
                "Drummer V3 placement coverage is too low "
                f"({drummer_ratio:.3f} < {MIN_DRUMMER_PLACEMENT_RATIO:.3f})"
            )
        missing_types = [
            drum_type
            for drum_type in REQUIRED_DRUM_TYPES
            if _positive_int(normalized_types.get(drum_type)) <= 0
        ]
        if missing_types:
            issues.append("Drummer V3 is missing final placements for: " + ", ".join(missing_types))

    components = {
        "root_participation": min(1.0, root_participation / 0.25),
        "visible_activity": min(1.0, mean_bright / 0.01),
        "spatial_spread": min(1.0, max_spread / 0.50),
        "channel_integrity": 1.0 if channel_overlaps == 0 else 0.0,
        "native_choreography": 1.0 if recovery_effects == 0 else 0.0,
    }
    if require_drummer:
        components["drummer_placement"] = drummer_ratio
    score = round(100.0 * sum(components.values()) / max(1, len(components)), 1)

    return {
        "schema": "helix.render_health.v1",
        "ok": not issues,
        "score": score,
        "issues": issues,
        "thresholds": {
            "min_root_model_participation_ratio": MIN_ROOT_PARTICIPATION_RATIO,
            "min_mean_bright_pixel_ratio": MIN_MEAN_BRIGHT_PIXEL_RATIO,
            "min_max_spread_ratio": MIN_MAX_SPREAD_RATIO,
            "min_density_samples": MIN_DENSITY_SAMPLES,
            "min_drummer_placement_ratio": MIN_DRUMMER_PLACEMENT_RATIO,
        },
        "metrics": {
            "model_effects": model_effects,
            "models_with_effects": models_with_effects,
            "root_model_participation_ratio": root_participation,
            "general_recovery_effects": recovery_effects,
            "channel_overlap_count": channel_overlaps,
            "density_sample_count": sample_count,
            "mean_bright_pixel_ratio": mean_bright,
            "max_spread_ratio": max_spread,
            "drummer_requests": drummer_requests,
            "drummer_placed": drummer_placed,
            "drummer_placement_ratio": round(drummer_ratio, 4),
            "drummer_placed_by_type": normalized_types,
        },
        "components": {key: round(value, 4) for key, value in components.items()},
        "require_drummer": bool(require_drummer),
        "require_native_choreography": bool(require_native_choreography),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate observable health of a finalized Helix preview."
    )
    parser.add_argument("--show-manifest", type=Path, required=True)
    parser.add_argument("--visual-density", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--require-drummer", action="store_true")
    parser.add_argument("--require-native-choreography", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assessment = evaluate_render_health(
        _load_json(args.show_manifest),
        _load_json(args.visual_density),
        require_drummer=args.require_drummer,
        require_native_choreography=args.require_native_choreography,
    )
    rendered = json.dumps(assessment, indent=2, sort_keys=True)
    print(rendered)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if assessment["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
