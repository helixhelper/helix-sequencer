#!/usr/bin/env python3
"""Validate a rendered outcome preview and describe its review bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from core import engine_profiles


MIN_ARTIFACT_BYTES = 1024
MAX_DURATION_RATIO = 1.05
MAX_DURATION_SLACK_SECONDS = 0.25
REQUIRED_DRUM_TYPES = ("kick", "snare", "hihat", "tom", "cymbal")


class PreviewArtifactError(RuntimeError):
    """Raised when the generated preview bundle is incomplete or unreadable."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_artifact(path: Path) -> None:
    if not path.is_file():
        raise PreviewArtifactError(f"Missing preview artifact: {path}")
    if path.stat().st_size < MIN_ARTIFACT_BYTES:
        raise PreviewArtifactError(
            f"Preview artifact is unexpectedly small ({path.stat().st_size} bytes): {path}"
        )


def _read_video_metadata(path: Path) -> dict[str, float | None]:
    import imageio.v2 as imageio

    reader = imageio.get_reader(str(path), "ffmpeg")
    try:
        metadata = reader.get_meta_data()
        first_frame = reader.get_data(0)
    finally:
        reader.close()
    if first_frame.size == 0:
        raise PreviewArtifactError(f"Preview has no decodable video frame: {path}")

    def number_or_none(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "duration": number_or_none(metadata.get("duration")),
        "fps": number_or_none(metadata.get("fps")),
    }


def _validate_audio_stream(path: Path) -> None:
    import imageio_ffmpeg

    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-t",
        "0.1",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or "no decodable audio stream"
        raise PreviewArtifactError(f"Preview audio validation failed for {path}: {detail}")


def read_xsq_duration_contract(path: Path) -> dict[str, float]:
    """Return declared duration and the latest effect boundary in an XSQ."""

    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise PreviewArtifactError(f"Cannot parse preview XSQ {path}: {exc}") from exc

    raw_duration = str(root.findtext("./head/sequenceDuration", default="") or "").strip()
    try:
        sequence_duration = float(raw_duration)
    except (TypeError, ValueError) as exc:
        raise PreviewArtifactError(
            f"Preview XSQ has invalid sequenceDuration {raw_duration!r}: {path}"
        ) from exc
    if sequence_duration <= 0:
        raise PreviewArtifactError(f"Preview XSQ has non-positive sequenceDuration: {path}")

    max_effect_end_ms = 0.0
    out_of_declared_range = 0
    for effect in root.findall("./ElementEffects//Effect"):
        try:
            end_ms = float(effect.attrib.get("endTime", "0") or 0)
        except (TypeError, ValueError):
            continue
        max_effect_end_ms = max(max_effect_end_ms, end_ms)
        if end_ms > (sequence_duration * 1000.0) + 1.0:
            out_of_declared_range += 1

    return {
        "sequence_duration_seconds": sequence_duration,
        "max_effect_end_seconds": max_effect_end_ms / 1000.0,
        "out_of_declared_range_effects": float(out_of_declared_range),
    }


def _maximum_allowed_duration(benchmark_duration_seconds: float) -> float:
    return max(
        1.0,
        float(benchmark_duration_seconds) * MAX_DURATION_RATIO + MAX_DURATION_SLACK_SECONDS,
    )


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _read_show_manifest(output_dir: Path, *, stem: str, required: bool) -> tuple[Path, dict[str, Any]]:
    show_path = output_dir / f"{stem}.show.json"
    if not show_path.is_file():
        if required:
            raise PreviewArtifactError(f"Preview proof requires finalized show manifest: {show_path}")
        return show_path, {}
    try:
        loaded = json.loads(show_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PreviewArtifactError(f"Cannot parse finalized show manifest {show_path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise PreviewArtifactError(f"Finalized show manifest is not a JSON object: {show_path}")
    return show_path, loaded


def _read_drummer_evidence(
    output_dir: Path,
    *,
    stem: str,
    report: dict[str, Any],
    required: bool,
    require_drum_classes: bool = False,
) -> dict[str, Any]:
    """Cross-check report and finalized-show evidence for Drummer V3 rendering."""

    report_drummer = report.get("drummer", {})
    if not isinstance(report_drummer, dict):
        report_drummer = {}
    review = report_drummer.get("review", {})
    if not isinstance(review, dict):
        review = {}

    show_path, show = _read_show_manifest(
        output_dir,
        stem=stem,
        required=required or require_drum_classes,
    )
    show_drummer = show.get("drummer", {}) if isinstance(show, dict) else {}
    if not isinstance(show_drummer, dict):
        show_drummer = {}
    placed_by_type = show_drummer.get("placed_by_type", {})
    if not isinstance(placed_by_type, dict):
        placed_by_type = {}
    normalized_by_type = {
        str(key).strip().lower(): _positive_int(value)
        for key, value in placed_by_type.items()
    }

    evidence = {
        "required": bool(required),
        "require_drum_classes": bool(require_drum_classes),
        "show_manifest": str(show_path),
        "show_manifest_exists": show_path.is_file(),
        "analyzed_cues": _positive_int(report_drummer.get("analyzed_cues")),
        "placement_requests": _positive_int(report_drummer.get("placement_requests")),
        "report_placed_effects": _positive_int(report_drummer.get("placed_effects")),
        "report_timing_track_events": _positive_int(report_drummer.get("timing_track_events")),
        "review_placed_cues": _positive_int(review.get("placed_cues")),
        "review_unplaced_cues": _positive_int(review.get("unplaced_cues")),
        "show_drummer_model_effects": _positive_int(show.get("drummer_model_effects")),
        "show_auto_drummer_timing_events": _positive_int(show.get("auto_drummer_timing_events")),
        "finalizer_timing_events": _positive_int(show_drummer.get("timing_events")),
        "finalizer_placed_effects": _positive_int(show_drummer.get("placed_effects")),
        "placed_by_type": normalized_by_type,
    }

    if required:
        checks = (
            ("analyzed cues", evidence["analyzed_cues"]),
            ("placement requests", evidence["placement_requests"]),
            ("report placed effects", evidence["report_placed_effects"]),
            ("report timing-track events", evidence["report_timing_track_events"]),
            ("final XSQ drummer model effects", evidence["show_drummer_model_effects"]),
            ("final XSQ AUTO Drummer timing events", evidence["show_auto_drummer_timing_events"]),
        )
        missing = [label for label, value in checks if _positive_int(value) <= 0]
        if missing:
            raise PreviewArtifactError(
                "Drummer V3 preview proof is incomplete; zero/missing " + ", ".join(missing)
            )

    if require_drum_classes:
        missing_types = [
            drum_type
            for drum_type in REQUIRED_DRUM_TYPES
            if _positive_int(normalized_by_type.get(drum_type)) <= 0
        ]
        if missing_types:
            raise PreviewArtifactError(
                "Drummer V3 class coverage is incomplete; zero/missing " + ", ".join(missing_types)
            )
    return evidence


def build_manifest(
    output_dir: Path,
    *,
    benchmark_duration_seconds: float,
    event: str,
    commit: str,
    require_drummer: bool = False,
    require_drum_classes: bool = False,
    require_native_choreography: bool = False,
) -> dict[str, Any]:
    profile = engine_profiles.active_profile()
    stem = "helix-outcome-preview"
    artifact_stem = f"{stem},{profile.version}"
    mp4 = output_dir / f"{artifact_stem}.mp4"
    xsq = output_dir / f"{artifact_stem}.xsq"
    report_path = output_dir / f"{artifact_stem}.report.json"

    for required_path in (mp4, xsq, report_path):
        _require_artifact(required_path)

    video = _read_video_metadata(mp4)
    _validate_audio_stream(mp4)
    rendered_duration = video["duration"]
    minimum_duration = max(1.0, float(benchmark_duration_seconds) * 0.95)
    maximum_duration = _maximum_allowed_duration(benchmark_duration_seconds)
    if rendered_duration is None or rendered_duration < minimum_duration:
        raise PreviewArtifactError(
            "Preview duration is shorter than the benchmark "
            f"({rendered_duration!r}s rendered; expected at least {minimum_duration:.2f}s)"
        )
    if rendered_duration > maximum_duration:
        raise PreviewArtifactError(
            "Preview duration extends beyond the benchmark "
            f"({rendered_duration:.2f}s rendered; expected at most {maximum_duration:.2f}s)"
        )

    xsq_duration = read_xsq_duration_contract(xsq)
    if xsq_duration["sequence_duration_seconds"] > maximum_duration:
        raise PreviewArtifactError(
            "Preview XSQ declares a duration beyond the benchmark "
            f"({xsq_duration['sequence_duration_seconds']:.2f}s; expected at most {maximum_duration:.2f}s)"
        )
    if xsq_duration["max_effect_end_seconds"] > maximum_duration:
        raise PreviewArtifactError(
            "Preview XSQ contains effects beyond the benchmark "
            f"(latest effect ends at {xsq_duration['max_effect_end_seconds']:.2f}s; "
            f"expected at most {maximum_duration:.2f}s)"
        )
    if int(xsq_duration["out_of_declared_range_effects"]) > 0:
        raise PreviewArtifactError(
            "Preview XSQ contains "
            f"{int(xsq_duration['out_of_declared_range_effects'])} effect(s) beyond sequenceDuration"
        )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    quality = report.get("quality", {})
    top_show = quality.get("top_show_benchmark", {})
    drummer = _read_drummer_evidence(
        output_dir,
        stem=artifact_stem,
        report=report,
        required=require_drummer,
        require_drum_classes=require_drum_classes,
    )
    show_path, show = _read_show_manifest(
        output_dir,
        stem=artifact_stem,
        required=require_native_choreography,
    )
    general_recovery_effects = _positive_int(show.get("general_effects_added"))
    if require_native_choreography and general_recovery_effects > 0:
        raise PreviewArtifactError(
            "Preview relied on beta recovery choreography instead of native engine model effects: "
            f"general_effects_added={general_recovery_effects} ({show_path})"
        )

    return {
        "schema": "helix.outcome_preview.v1",
        "event": event,
        "commit": commit,
        "profile_id": engine_profiles.ACTIVE_PROFILE_ID,
        "profile_version": profile.version,
        "benchmark_duration_seconds": float(benchmark_duration_seconds),
        "maximum_allowed_duration_seconds": maximum_duration,
        "rendered_duration_seconds": rendered_duration,
        "rendered_fps": video["fps"],
        "sequence_duration_seconds": xsq_duration["sequence_duration_seconds"],
        "max_effect_end_seconds": xsq_duration["max_effect_end_seconds"],
        "out_of_declared_range_effects": int(xsq_duration["out_of_declared_range_effects"]),
        "audio_stream_validated": True,
        "quality_score": quality.get("score"),
        "quality_grade": quality.get("grade"),
        "top_show_score": top_show.get("score"),
        "top_show_grade": top_show.get("grade"),
        "native_choreography_required": bool(require_native_choreography),
        "general_recovery_effects": general_recovery_effects,
        "drummer": drummer,
        "preview_mp4": str(mp4),
        "preview_mp4_bytes": mp4.stat().st_size,
        "preview_mp4_sha256": sha256_file(mp4),
        "sequence_xsq": str(xsq),
        "sequence_xsq_sha256": sha256_file(xsq),
        "report": str(report_path),
    }


def render_summary(manifest: dict[str, Any]) -> str:
    drummer = manifest.get("drummer", {})
    if not isinstance(drummer, dict):
        drummer = {}
    drummer_summary = (
        f"{_positive_int(drummer.get('analyzed_cues'))} analyzed / "
        f"{_positive_int(drummer.get('report_placed_effects'))} placed / "
        f"{_positive_int(drummer.get('show_drummer_model_effects'))} final model effects"
    )
    return "\n".join(
        [
            "# Helix outcome preview",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Commit | `{manifest['commit']}` |",
            (
                f"| Active profile | `{manifest['profile_id']}` "
                f"(`{manifest['profile_version']}`) |"
            ),
            (
                "| Benchmark | Deterministic synthetic audio, "
                f"{manifest['benchmark_duration_seconds']:.0f}s |"
            ),
            f"| Rendered duration | {manifest['rendered_duration_seconds']:.2f}s |",
            f"| XSQ duration | {manifest['sequence_duration_seconds']:.2f}s |",
            f"| Latest effect | {manifest['max_effect_end_seconds']:.2f}s |",
            f"| Native choreography recovery effects | {manifest['general_recovery_effects']} |",
            f"| Drummer V3 | {drummer_summary} |",
            f"| Drummer classes | {drummer.get('placed_by_type', {})} |",
            f"| Preview | `{Path(manifest['preview_mp4']).name}` |",
            f"| Quality | {manifest['quality_score']} ({manifest['quality_grade']}) |",
            (
                "| Top-show benchmark | "
                f"{manifest['top_show_score']} ({manifest['top_show_grade']}) |"
            ),
            f"| MP4 SHA-256 | `{manifest['preview_mp4_sha256']}` |",
            "",
            "The bundle also contains the generated XSQ, quality report, manifest, and contact sheets.",
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a Helix outcome preview and write its artifact manifest."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--benchmark-duration", type=float, required=True)
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME", "local"))
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", "local"))
    parser.add_argument("--summary-out", type=Path, default=Path("review_summary.md"))
    parser.add_argument(
        "--require-drummer",
        action="store_true",
        help="Fail unless the report and finalized XSQ prove Drummer V3 cues were rendered.",
    )
    parser.add_argument(
        "--require-drum-classes",
        action="store_true",
        help="Fail unless kick, snare, hihat, tom, and cymbal each have final placements.",
    )
    parser.add_argument(
        "--require-native-choreography",
        action="store_true",
        help="Fail if the benchmark needed beta recovery effects to reach model participation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_manifest(
        args.output_dir,
        benchmark_duration_seconds=args.benchmark_duration,
        event=args.event,
        commit=args.commit,
        require_drummer=args.require_drummer,
        require_drum_classes=args.require_drum_classes,
        require_native_choreography=args.require_native_choreography,
    )
    manifest_path = args.output_dir / "outcome-preview-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.summary_out.write_text(render_summary(manifest), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())