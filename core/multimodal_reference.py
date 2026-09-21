from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.lms_calibration import (
    ReferenceCalibrationProfile,
    ReferenceSectionTarget,
    calibration_from_report,
    inspect_lms,
)


@dataclass(frozen=True)
class SectionSpec:
    label: str
    start_seconds: float
    end_seconds: float


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_section_specs(path: str | Path) -> tuple[SectionSpec, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_sections = payload.get("sections", payload) if isinstance(payload, Mapping) else payload
    if not isinstance(raw_sections, list):
        raise ValueError("Section specification must be a list or contain a sections list.")
    sections = tuple(
        SectionSpec(
            label=str(item["label"]),
            start_seconds=float(item["start_seconds"]),
            end_seconds=float(item["end_seconds"]),
        )
        for item in raw_sections
    )
    if not sections:
        raise ValueError("At least one reference section is required.")
    previous_end = 0.0
    for section in sections:
        if section.start_seconds < previous_end or section.end_seconds <= section.start_seconds:
            raise ValueError("Reference sections must be ordered, non-overlapping, and non-empty.")
        previous_end = section.end_seconds
    return sections


def _video_metrics(
    video_path: Path,
    sections: Iterable[SectionSpec],
    *,
    offset_seconds: float,
    sample_fps: float = 4.0,
) -> dict[str, dict[str, float]]:
    """Measure audience-visible brightness, contrast, motion and darkness.

    Sampling is deliberately sparse and aggregate-only. No frame, timestamp, or
    pixel data is serialized into the resulting calibration bundle.
    """

    import imageio.v2 as imageio
    import numpy as np

    wanted = tuple(sections)
    accum: dict[str, dict[str, Any]] = {
        item.label: {"luma": [], "contrast": [], "motion": [], "dark": [], "previous": None}
        for item in wanted
    }
    reader = imageio.get_reader(str(video_path), "ffmpeg")
    try:
        metadata = reader.get_meta_data()
        source_fps = max(0.001, float(metadata.get("fps") or 30.0))
        stride = max(1, int(round(source_fps / max(0.1, sample_fps))))
        for index, frame in enumerate(reader):
            if index % stride:
                continue
            audio_seconds = (index / source_fps) - float(offset_seconds)
            section = next(
                (item for item in wanted if item.start_seconds <= audio_seconds < item.end_seconds),
                None,
            )
            if section is None:
                continue
            array = np.asarray(frame, dtype=np.float32)
            if array.ndim == 3 and array.shape[2] >= 3:
                luma = (array[..., 0] * 0.2126 + array[..., 1] * 0.7152 + array[..., 2] * 0.0722) / 255.0
            else:
                luma = array / 255.0
            bucket = accum[section.label]
            bucket["luma"].append(float(np.mean(luma)))
            bucket["contrast"].append(float(np.std(luma)))
            bucket["dark"].append(float(np.mean(luma < 0.10)))
            previous = bucket["previous"]
            if previous is not None and previous.shape == luma.shape:
                bucket["motion"].append(float(np.mean(np.abs(luma - previous))))
            bucket["previous"] = luma
    finally:
        reader.close()

    def average(values: list[float]) -> float:
        return round(sum(values) / len(values), 6) if values else 0.0

    return {
        label: {
            "video_mean_luma": average(bucket["luma"]),
            "video_contrast": average(bucket["contrast"]),
            "video_motion": average(bucket["motion"]),
            "video_dark_fraction": average(bucket["dark"]),
        }
        for label, bucket in accum.items()
    }


def _structural_section_targets(
    lms_path: Path,
    sections: Iterable[SectionSpec],
    *,
    grid_ms: int,
) -> dict[str, dict[str, float | int]]:
    """Derive section aggregates without exporting event-level choreography."""

    import xml.etree.ElementTree as ET

    from core import lms_calibration as lms

    root = ET.parse(lms_path).getroot()
    channels = lms._root_channels(root)
    physical = [item for item in channels if lms._is_controller_backed(item)] or channels
    records = lms._extract_effect_records(root, channels, physical)
    output: dict[str, dict[str, float | int]] = {}
    for section in sections:
        start_cs = int(round(section.start_seconds * 100.0))
        end_cs = int(round(section.end_seconds * 100.0))
        selected = [item for item in records if start_cs <= item.start_cs < end_cs]
        durations = [item.duration_ms for item in selected if item.duration_ms > 0]
        starts = [item.start_cs * 10 for item in selected]
        alignment = (
            sum(1 for value in starts if grid_ms > 0 and value % grid_ms == 0) / len(starts)
            if starts and grid_ms > 0
            else 0.0
        )
        normalized = [
            lms._EffectRecord(
                channel_key=item.channel_key,
                start_cs=max(0, item.start_cs - start_cs),
                end_cs=min(end_cs - start_cs, max(0, item.end_cs - start_cs)),
                effect_type=item.effect_type,
                shape=item.shape,
            )
            for item in selected
        ]
        mean_active, _p90, _peak = lms._activity_stats(
            normalized,
            channel_count=len(physical),
            duration_cs=max(1, end_cs - start_cs),
        )
        output[section.label] = {
            "effect_count": len(selected),
            "timing_grid_alignment": round(alignment, 6),
            "median_effect_ms": lms._percentile(durations, 0.5),
            "mean_active_fraction": mean_active,
        }
    return output


def build_multimodal_reference(
    *,
    lms_path: str | Path,
    video_path: str | Path,
    section_spec_path: str | Path,
    audio_path: str | Path | None = None,
    video_offset_seconds: float = 0.0,
    acknowledge_reference_rights: bool = False,
) -> dict[str, Any]:
    if not acknowledge_reference_rights:
        raise PermissionError("Building a reference profile requires explicit rights acknowledgement.")
    lms_source = Path(lms_path)
    video_source = Path(video_path)
    audio_source = Path(audio_path) if audio_path else None
    for source in (lms_source, video_source, audio_source):
        if source is not None and not source.is_file():
            raise FileNotFoundError(source)

    sections = load_section_specs(section_spec_path)
    base = calibration_from_report(inspect_lms(lms_source))
    structural = _structural_section_targets(lms_source, sections, grid_ms=base.timing_grid_ms)
    visual = _video_metrics(video_source, sections, offset_seconds=video_offset_seconds)
    targets = tuple(
        ReferenceSectionTarget(
            label=section.label,
            start_seconds=section.start_seconds,
            end_seconds=section.end_seconds,
            **structural[section.label],
            **visual[section.label],
        )
        for section in sections
    )
    profile = ReferenceCalibrationProfile(
        **{
            **base.to_dict(),
            "schema": "helix.reference_calibration.v2",
            "audio_sha256": _sha256(audio_source) if audio_source else "",
            "video_sha256": _sha256(video_source),
            "video_offset_seconds": round(float(video_offset_seconds), 6),
            "sections": targets,
        }
    )
    return {
        "schema": "helix.multimodal_reference.v1",
        "privacy_mode": "aggregate_only",
        "calibration": profile.to_dict(),
        "provenance": {
            "lms_sha256": base.source_sha256,
            "audio_sha256": profile.audio_sha256,
            "video_sha256": profile.video_sha256,
            "section_count": len(targets),
        },
    }


def write_multimodal_reference(path: str | Path, payload: Mapping[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def compare_candidate_video(
    *,
    candidate_video_path: str | Path,
    profile: ReferenceCalibrationProfile,
    sample_fps: float = 4.0,
) -> dict[str, Any]:
    """Compare a rendered candidate with the physical reference by section."""

    if not profile.sections:
        raise ValueError("Reference calibration has no section-level video targets.")
    candidate = Path(candidate_video_path)
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    specs = tuple(
        SectionSpec(item.label, item.start_seconds, item.end_seconds)
        for item in profile.sections
    )
    observed = _video_metrics(candidate, specs, offset_seconds=0.0, sample_fps=sample_fps)

    def similarity(actual: float, target: float, tolerance: float) -> float:
        return max(0.0, 1.0 - abs(float(actual) - float(target)) / tolerance)

    tolerances = {
        "video_mean_luma": 0.35,
        "video_contrast": 0.25,
        "video_motion": 0.20,
        "video_dark_fraction": 0.40,
    }
    comparisons: list[dict[str, Any]] = []
    for target in profile.sections:
        actual = observed.get(target.label, {})
        component_scores = {
            key: similarity(float(actual.get(key, 0.0)), float(getattr(target, key)), tolerance)
            for key, tolerance in tolerances.items()
        }
        score = sum(component_scores.values()) / len(component_scores)
        comparisons.append(
            {
                "label": target.label,
                "start_seconds": target.start_seconds,
                "end_seconds": target.end_seconds,
                "score": round(score * 100.0, 2),
                "component_scores": {
                    key.removeprefix("video_"): round(value * 100.0, 2)
                    for key, value in component_scores.items()
                },
                "reference": {
                    key.removeprefix("video_"): round(float(getattr(target, key)), 6)
                    for key in tolerances
                },
                "candidate": {
                    key.removeprefix("video_"): round(float(actual.get(key, 0.0)), 6)
                    for key in tolerances
                },
            }
        )
    overall = sum(item["score"] for item in comparisons) / len(comparisons)
    return {
        "schema": "helix.multimodal_comparison.v1",
        "privacy_mode": "aggregate_only",
        "candidate_video_sha256": _sha256(candidate),
        "reference_video_sha256": profile.video_sha256,
        "overall_score": round(overall, 2),
        "sections": comparisons,
    }
