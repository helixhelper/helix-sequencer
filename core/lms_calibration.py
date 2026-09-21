from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


GRID_CANDIDATES_MS = (10, 20, 25, 50, 100, 250, 500)
MIN_GRID_ALIGNMENT = 0.75
_NON_PHYSICAL_DEVICE_TYPES = {"", "sequence", "track", "timing", "timinggrid"}


@dataclass(frozen=True)
class _EffectRecord:
    channel_key: str
    start_cs: int
    end_cs: int
    effect_type: str
    shape: str

    @property
    def duration_ms(self) -> int:
        return max(0, (self.end_cs - self.start_cs) * 10)


@dataclass(frozen=True)
class LmsInspectionReport:
    """Aggregate LMS measurements.

    The inspection report may identify the local source path for CLI usability.
    Runtime calibration uses :class:`ReferenceCalibrationProfile` instead, which
    intentionally omits paths, channel names, and event-level timing data.
    """

    schema: str = "helix.lms_inspection.v1"
    analysis_version: int = 2
    source_path: str = ""
    source_sha256: str = ""
    file_size_bytes: int = 0
    xml_root: str = ""
    probable_channel_count: int = 0
    channel_tag_count: int = 0
    root_channel_count: int = 0
    physical_channel_count: int = 0
    active_effect_channel_count: int = 0
    archived_channel_count: int = 0
    event_like_tag_count: int = 0
    unique_event_tag_count: int = 0
    physical_effect_count: int = 0
    probable_duration_seconds: float = 0.0
    timing_density_events_per_second: float = 0.0
    effects_per_channel_second: float = 0.0
    effect_hints: dict[str, int] = field(default_factory=dict)
    effect_type_counts: dict[str, int] = field(default_factory=dict)
    effect_shape_counts: dict[str, int] = field(default_factory=dict)
    median_effect_ms: int = 0
    p90_effect_ms: int = 0
    start_alignment_by_grid_ms: dict[str, float] = field(default_factory=dict)
    inferred_grid_ms: int = 0
    inferred_grid_alignment: float = 0.0
    mean_active_fraction: float = 0.0
    p90_active_fraction: float = 0.0
    peak_active_fraction: float = 0.0
    common_tags: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


@dataclass(frozen=True)
class ReferenceSectionTarget:
    """Aggregate structural and physical-video targets for one song section."""

    label: str
    start_seconds: float
    end_seconds: float
    effect_count: int = 0
    timing_grid_alignment: float = 0.0
    median_effect_ms: int = 0
    mean_active_fraction: float = 0.0
    video_mean_luma: float = 0.0
    video_contrast: float = 0.0
    video_motion: float = 0.0
    video_dark_fraction: float = 0.0

    def contains_ms(self, value: int) -> bool:
        seconds = float(value) / 1000.0
        return self.start_seconds <= seconds < self.end_seconds


@dataclass(frozen=True)
class ReferenceCalibrationProfile:
    """Safe, aggregate-only targets derived from a licensed reference LMS."""

    schema: str = "helix.reference_calibration.v2"
    source_kind: str = "lms_aggregate"
    source_sha256: str = ""
    source_file_size_bytes: int = 0
    duration_seconds: float = 0.0
    physical_channel_count: int = 0
    effect_count: int = 0
    effects_per_channel_second: float = 0.0
    timing_grid_ms: int = 0
    timing_grid_alignment: float = 0.0
    median_effect_ms: int = 0
    p90_effect_ms: int = 0
    shimmer_share: float = 0.0
    fade_share: float = 0.0
    fixed_share: float = 0.0
    mean_active_fraction: float = 0.0
    p90_active_fraction: float = 0.0
    peak_active_fraction: float = 0.0
    audio_sha256: str = ""
    video_sha256: str = ""
    video_offset_seconds: float = 0.0
    sections: tuple[ReferenceSectionTarget, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceCalibrationProfile":
        allowed = set(cls.__dataclass_fields__)
        values = {key: value for key, value in payload.items() if key in allowed and key != "sections"}
        values["sections"] = tuple(
            ReferenceSectionTarget(**item)
            for item in payload.get("sections", [])
            if isinstance(item, Mapping)
        )
        return cls(**values)


@dataclass
class CalibrationApplication:
    """Per-run calibration decisions; contains no reference choreography."""

    profile: ReferenceCalibrationProfile
    strength: float = 1.0
    effect_candidates: int = 0
    shimmer_candidates: int = 0
    shimmer_kept: int = 0
    shimmer_replaced: int = 0
    ramp_replacements: int = 0
    on_replacements: int = 0
    ramp_outputs: int = 0
    timing_considered: int = 0
    timing_snapped: int = 0
    duration_considered: int = 0
    duration_adjusted: int = 0
    section_decisions: Counter[str] = field(default_factory=Counter)

    def __post_init__(self) -> None:
        self.strength = _clamp(float(self.strength), 0.0, 1.0)

    def tune_effect(self, effect_name: str, *, stable_key: str) -> str:
        """Suppress excess Shimmer and replace it with reference-like envelopes."""

        name = str(effect_name or "On").strip() or "On"
        self.effect_candidates += 1
        if name.lower() != "shimmer":
            if name.lower() == "ramp":
                self.ramp_outputs += 1
            return name
        self.shimmer_candidates += 1

        # A strength below one leaves a deterministic portion untouched. At full
        # strength, the online quota makes Shimmer approach the reference's share
        # of all effect candidates rather than its share of Shimmer candidates.
        if _stable_fraction(stable_key, "shimmer-calibration") >= self.strength:
            self.shimmer_kept += 1
            return name
        allowed_shimmer = int(math.floor(self.effect_candidates * self.profile.shimmer_share))
        if self.shimmer_kept < allowed_shimmer:
            self.shimmer_kept += 1
            return name

        self.shimmer_replaced += 1
        desired_ramp_outputs = int(math.ceil(self.effect_candidates * self.profile.fade_share))
        if self.ramp_outputs < desired_ramp_outputs:
            self.ramp_replacements += 1
            self.ramp_outputs += 1
            return "Ramp"
        self.on_replacements += 1
        return "On"

    def tune_range(
        self,
        start_ms: int,
        end_ms: int,
        *,
        stable_key: str,
        min_duration_ms: int,
    ) -> tuple[int, int]:
        """Blend duration and timing-grid targets into one placement."""

        st = int(start_ms)
        en = max(st + 1, int(end_ms))
        minimum = max(1, int(min_duration_ms))
        section = next((item for item in self.profile.sections if item.contains_ms(st)), None)
        if section is not None:
            self.section_decisions[section.label] += 1
        target_duration = max(
            minimum,
            int(section.median_effect_ms if section and section.median_effect_ms else self.profile.median_effect_ms),
        )
        self.duration_considered += 1
        reference_activity = (
            section.mean_active_fraction
            if section and section.mean_active_fraction
            else self.profile.mean_active_fraction or 0.5
        )
        duration_probability = self.strength * _clamp(reference_activity, 0.25, 0.75)
        if (
            target_duration > 0
            and en - st < target_duration
            and _stable_fraction(stable_key, "duration-calibration") < duration_probability
        ):
            en = st + target_duration
            self.duration_adjusted += 1

        grid_ms = max(0, int(self.profile.timing_grid_ms))
        self.timing_considered += 1
        alignment = (
            section.timing_grid_alignment
            if section and section.timing_grid_alignment
            else self.profile.timing_grid_alignment
        )
        snap_probability = self.strength * _clamp(alignment, 0.0, 1.0)
        if grid_ms > 0 and _stable_fraction(stable_key, "grid-calibration") < snap_probability:
            st = _round_to_grid(st, grid_ms)
            en = _round_to_grid(en, grid_ms)
            if en < st + minimum:
                en = st + max(minimum, grid_ms)
            self.timing_snapped += 1
        return st, en

    def decision_summary(self) -> dict[str, Any]:
        return {
            "effect_candidates": self.effect_candidates,
            "shimmer_candidates": self.shimmer_candidates,
            "shimmer_kept": self.shimmer_kept,
            "shimmer_replaced": self.shimmer_replaced,
            "ramp_replacements": self.ramp_replacements,
            "on_replacements": self.on_replacements,
            "ramp_outputs": self.ramp_outputs,
            "timing_considered": self.timing_considered,
            "timing_snapped": self.timing_snapped,
            "duration_considered": self.duration_considered,
            "duration_adjusted": self.duration_adjusted,
            "section_decisions": dict(sorted(self.section_decisions.items())),
        }


def _local_name(tag: str) -> str:
    return str(tag).split("}", 1)[-1].lower()


def _attrs(element: ET.Element) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in element.attrib.items()}


def _intish(value: object) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", str(value).strip())
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _stable_fraction(*parts: str) -> float:
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _round_to_grid(value: int, grid_ms: int) -> int:
    if grid_ms <= 0:
        return int(value)
    return int(math.floor((int(value) + grid_ms / 2.0) / grid_ms) * grid_ms)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    wanted = name.lower()
    return [child for child in list(element) if _local_name(child.tag) == wanted]


def _root_channels(root: ET.Element) -> list[ET.Element]:
    containers = _direct_children(root, "channels")
    if not containers:
        return []
    return _direct_children(containers[0], "channel")


def _is_controller_backed(channel: ET.Element) -> bool:
    attrs = _attrs(channel)
    device_type = attrs.get("devicetype", "").strip().lower()
    if device_type and device_type not in _NON_PHYSICAL_DEVICE_TYPES:
        return True
    return any(key in attrs for key in ("unit", "circuit", "network", "universe", "address"))


def _effect_type(element: ET.Element) -> str:
    attrs = _attrs(element)
    raw = (attrs.get("type") or attrs.get("effecttype") or "").strip().lower()
    text = " ".join((raw, (element.text or "").strip().lower()))
    if "shimmer" in text:
        return "shimmer"
    if "twinkle" in text:
        return "twinkle"
    if any(token in text for token in ("chase", "wave", "sweep")):
        return "chase"
    if re.search(r"\boff\b", text):
        return "off"
    if raw == "intensity" or any(token in text for token in ("fade", "ramp")) or re.search(r"\bon\b", text):
        return "intensity"
    return raw or "unknown"


def _effect_shape(element: ET.Element, effect_type: str) -> str:
    attrs = _attrs(element)
    start = _intish(attrs.get("startintensity"))
    end = _intish(attrs.get("endintensity"))
    if start is not None and end is not None:
        if end > start:
            return "fade_up"
        if end < start:
            return "fade_down"
        return "fixed"
    text = (element.text or "").strip().lower()
    if "fade up" in text or "ramp up" in text:
        return "fade_up"
    if "fade down" in text or "ramp down" in text or "twinklefade" in text:
        return "fade_down"
    if effect_type in {"intensity", "shimmer", "twinkle", "off"}:
        return "fixed"
    return "unknown"


def _channel_key(channel: ET.Element, index: int) -> str:
    attrs = _attrs(channel)
    # Keys exist only while aggregating concurrency and never leave this module.
    return (
        attrs.get("id")
        or attrs.get("savedindex")
        or attrs.get("name")
        or f"channel-{index}"
    )


def _record_from_effect(element: ET.Element, channel_key: str) -> _EffectRecord | None:
    attrs = _attrs(element)
    start = _intish(
        attrs.get("startcentisecond")
        or attrs.get("startcs")
        or attrs.get("start")
        or attrs.get("time")
    )
    end = _intish(
        attrs.get("endcentisecond")
        or attrs.get("endcs")
        or attrs.get("end")
    )
    if start is None:
        return None
    if end is None:
        end = start
    if end < start:
        start, end = end, start
    effect_type = _effect_type(element)
    return _EffectRecord(
        channel_key=channel_key,
        start_cs=max(0, start),
        end_cs=max(0, end),
        effect_type=effect_type,
        shape=_effect_shape(element, effect_type),
    )


def _extract_effect_records(
    root: ET.Element,
    root_channels: Sequence[ET.Element],
    physical_channels: Sequence[ET.Element],
) -> list[_EffectRecord]:
    records: list[_EffectRecord] = []
    for index, channel in enumerate(physical_channels):
        key = _channel_key(channel, index)
        for element in channel.iter():
            if _local_name(element.tag) != "effect":
                continue
            record = _record_from_effect(element, key)
            if record is not None:
                records.append(record)
    if records:
        return records

    # Some older LMS exports keep channel definitions and effects in separate
    # track nodes. This fallback is used only when controller channels do not
    # contain effects, avoiding duplicate archived track data in modern files.
    known_keys = {
        candidate
        for index, channel in enumerate(root_channels)
        for candidate in (
            _attrs(channel).get("id"),
            _attrs(channel).get("channel"),
            _attrs(channel).get("savedindex"),
            _channel_key(channel, index),
        )
        if candidate is not None
    }
    for index, element in enumerate(root.iter()):
        if _local_name(element.tag) != "effect":
            continue
        attrs = _attrs(element)
        key = attrs.get("channel") or attrs.get("channelid") or attrs.get("channel_id") or f"event-{index}"
        if known_keys and key not in known_keys and "channel" in attrs:
            continue
        record = _record_from_effect(element, key)
        if record is not None:
            records.append(record)
    return records


def _extract_duration_cs(root: ET.Element, records: Sequence[_EffectRecord]) -> int:
    values = [record.end_cs for record in records]
    for element in root.iter():
        attrs = _attrs(element)
        for key in (
            "centisecond",
            "centiseconds",
            "startcentisecond",
            "endcentisecond",
            "startcs",
            "endcs",
        ):
            value = _intish(attrs.get(key))
            if value is not None and value >= 0:
                values.append(value)
    return max(values, default=0)


def _percentile(values: Sequence[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(int(value) for value in values)
    rank = _clamp(percentile, 0.0, 1.0) * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    weight = rank - low
    return int(round(ordered[low] * (1.0 - weight) + ordered[high] * weight))


def _merge_intervals(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted((int(start), int(end)) for start, end in intervals if end > start):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _activity_stats(
    records: Sequence[_EffectRecord],
    *,
    channel_count: int,
    duration_cs: int,
) -> tuple[float, float, float]:
    if not records or channel_count <= 0 or duration_cs <= 0:
        return 0.0, 0.0, 0.0
    by_channel: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for record in records:
        if record.end_cs > record.start_cs:
            by_channel[record.channel_key].append((record.start_cs, record.end_cs))

    deltas: Counter[int] = Counter()
    active_cs = 0
    for intervals in by_channel.values():
        for start, end in _merge_intervals(intervals):
            active_cs += end - start
            deltas[start] += 1
            deltas[end] -= 1

    current = 0
    previous = 0
    peak = 0
    weighted_counts: Counter[int] = Counter()
    for moment in sorted(deltas):
        if moment > previous:
            weighted_counts[current] += moment - previous
        current += deltas[moment]
        peak = max(peak, current)
        previous = moment
    if previous < duration_cs:
        weighted_counts[current] += duration_cs - previous

    threshold = duration_cs * 0.90
    accumulated = 0
    p90_count = 0
    for count, weight in sorted(weighted_counts.items()):
        accumulated += weight
        if accumulated >= threshold:
            p90_count = count
            break
    denominator = channel_count * duration_cs
    return (
        round(active_cs / denominator, 6),
        round(p90_count / channel_count, 6),
        round(peak / channel_count, 6),
    )


def _effect_hints(records: Sequence[_EffectRecord]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        if record.effect_type == "shimmer":
            counts["shimmer"] += 1
        elif record.effect_type == "twinkle":
            counts["twinkle"] += 1
        elif record.effect_type == "chase":
            counts["chase"] += 1
        elif record.effect_type == "off":
            counts["off"] += 1
        if record.shape in {"fade_up", "fade_down"}:
            counts["fade"] += 1
        elif record.effect_type == "intensity":
            counts["on"] += 1
    return dict(sorted(counts.items()))


def inspect_lms(path: str | Path) -> LmsInspectionReport:
    source = Path(path)
    if not source.exists():
        return LmsInspectionReport(source_path=str(source), warnings=[f"Missing LMS file: {source}"])
    try:
        root = ET.parse(source).getroot()
    except (ET.ParseError, OSError) as exc:
        size = source.stat().st_size if source.exists() else 0
        return LmsInspectionReport(
            source_path=str(source),
            file_size_bytes=size,
            warnings=[f"Could not parse LMS XML: {exc}"],
        )

    tag_counts = Counter(_local_name(element.tag) for element in root.iter())
    channels = _root_channels(root)
    typed_physical = [channel for channel in channels if _is_controller_backed(channel)]
    physical_channels = typed_physical or channels
    records = _extract_effect_records(root, channels, physical_channels)
    active_effect_channels = len({record.channel_key for record in records})
    duration_cs = _extract_duration_cs(root, records)
    duration_seconds = round(duration_cs / 100.0, 3) if duration_cs > 0 else 0.0
    durations_ms = [record.duration_ms for record in records if record.duration_ms > 0]
    starts_ms = [record.start_cs * 10 for record in records]
    type_counts = Counter(record.effect_type for record in records)
    shape_counts = Counter(record.shape for record in records)
    alignments = {
        str(grid): round(sum(1 for value in starts_ms if value % grid == 0) / len(starts_ms), 6)
        for grid in GRID_CANDIDATES_MS
    } if starts_ms else {}
    eligible_grids = [
        grid for grid in GRID_CANDIDATES_MS
        if alignments.get(str(grid), 0.0) >= MIN_GRID_ALIGNMENT
    ]
    inferred_grid = max(eligible_grids, default=0)
    inferred_alignment = alignments.get(str(inferred_grid), 0.0) if inferred_grid else 0.0
    mean_active, p90_active, peak_active = _activity_stats(
        records,
        channel_count=len(physical_channels),
        duration_cs=duration_cs,
    )
    archived_channels = sum(
        1
        for track in root.iter()
        if _local_name(track.tag) == "track"
        for element in track.iter()
        if element is not track and _local_name(element.tag) == "channel"
    )
    warnings: list[str] = []
    if not channels:
        warnings.append("No root LMS channel definitions found.")
    if not typed_physical and channels:
        warnings.append("No controller-backed channel metadata found; using root channel definitions.")
    if not records:
        warnings.append("No timed effects found on active channels.")
    if duration_seconds <= 0:
        warnings.append("No obvious LMS timing/duration values found.")

    effect_count = len(records)
    density = effect_count / duration_seconds if duration_seconds > 0 else 0.0
    per_channel_second = (
        effect_count / len(physical_channels) / duration_seconds
        if physical_channels and duration_seconds > 0
        else 0.0
    )
    return LmsInspectionReport(
        source_path=str(source),
        source_sha256=_sha256(source),
        file_size_bytes=source.stat().st_size,
        xml_root=_local_name(root.tag),
        probable_channel_count=len(physical_channels),
        channel_tag_count=int(tag_counts.get("channel", 0)),
        root_channel_count=len(channels),
        physical_channel_count=len(physical_channels),
        active_effect_channel_count=active_effect_channels,
        archived_channel_count=archived_channels,
        event_like_tag_count=effect_count,
        unique_event_tag_count=1 if effect_count else 0,
        physical_effect_count=effect_count,
        probable_duration_seconds=duration_seconds,
        timing_density_events_per_second=round(density, 4),
        effects_per_channel_second=round(per_channel_second, 6),
        effect_hints=_effect_hints(records),
        effect_type_counts=dict(sorted(type_counts.items())),
        effect_shape_counts=dict(sorted(shape_counts.items())),
        median_effect_ms=_percentile(durations_ms, 0.50),
        p90_effect_ms=_percentile(durations_ms, 0.90),
        start_alignment_by_grid_ms=alignments,
        inferred_grid_ms=inferred_grid,
        inferred_grid_alignment=round(inferred_alignment, 6),
        mean_active_fraction=mean_active,
        p90_active_fraction=p90_active,
        peak_active_fraction=peak_active,
        common_tags=dict(tag_counts.most_common(15)),
        warnings=warnings,
    )


def calibration_from_report(report: LmsInspectionReport) -> ReferenceCalibrationProfile:
    if report.physical_effect_count <= 0 or report.probable_duration_seconds <= 0:
        detail = "; ".join(report.warnings) or "no usable active-channel effects"
        raise ValueError(f"LMS cannot produce a calibration profile: {detail}")
    effect_count = report.physical_effect_count
    shape_counts = report.effect_shape_counts
    fade_count = int(shape_counts.get("fade_up", 0)) + int(shape_counts.get("fade_down", 0))
    fixed_count = int(shape_counts.get("fixed", 0))
    shimmer_count = int(report.effect_type_counts.get("shimmer", 0))
    return ReferenceCalibrationProfile(
        source_sha256=report.source_sha256,
        source_file_size_bytes=report.file_size_bytes,
        duration_seconds=report.probable_duration_seconds,
        physical_channel_count=report.physical_channel_count,
        effect_count=effect_count,
        effects_per_channel_second=report.effects_per_channel_second,
        timing_grid_ms=report.inferred_grid_ms,
        timing_grid_alignment=report.inferred_grid_alignment,
        median_effect_ms=report.median_effect_ms,
        p90_effect_ms=report.p90_effect_ms,
        shimmer_share=round(shimmer_count / effect_count, 6),
        fade_share=round(fade_count / effect_count, 6),
        fixed_share=round(fixed_count / effect_count, 6),
        mean_active_fraction=report.mean_active_fraction,
        p90_active_fraction=report.p90_active_fraction,
        peak_active_fraction=report.peak_active_fraction,
    )


def load_lms_calibration(path: str | Path) -> ReferenceCalibrationProfile:
    source = Path(path)
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("schema") == "helix.multimodal_reference.v1":
            payload = payload.get("calibration", {})
        if not isinstance(payload, Mapping):
            raise ValueError("Reference calibration JSON must contain an object.")
        return ReferenceCalibrationProfile.from_dict(payload)
    return calibration_from_report(inspect_lms(source))


def summarize_calibration_result(
    application: CalibrationApplication,
    placements: Iterable[tuple[int, int, str]],
) -> dict[str, Any]:
    """Return aggregate target/achievement data for the generated report."""

    placed = [(int(start), int(end), str(effect)) for start, end, effect in placements if end > start]
    starts = [start for start, _end, _effect in placed]
    durations = [end - start for start, end, _effect in placed]
    names = Counter(effect.strip().lower() for _start, _end, effect in placed)
    total = len(placed)
    profile = application.profile
    grid = profile.timing_grid_ms
    achieved_alignment = (
        sum(1 for start in starts if grid > 0 and start % grid == 0) / total
        if total and grid > 0
        else 0.0
    )
    achieved_shimmer = names.get("shimmer", 0) / total if total else 0.0
    achieved_fade = names.get("ramp", 0) / total if total else 0.0
    achieved_fixed = names.get("on", 0) / total if total else 0.0
    achieved_median = _percentile(durations, 0.50)
    achieved_p90 = _percentile(durations, 0.90)

    def closeness(actual: float, target: float, floor: float) -> float:
        return _clamp(1.0 - abs(actual - target) / max(floor, abs(target)), 0.0, 1.0)

    components = {
        "timing_grid": closeness(achieved_alignment, profile.timing_grid_alignment, 0.10),
        "median_duration": closeness(float(achieved_median), float(profile.median_effect_ms), 100.0),
        "shimmer_share": closeness(achieved_shimmer, profile.shimmer_share, 0.05),
        "fade_share": closeness(achieved_fade, profile.fade_share, 0.20),
    }
    score = round(100.0 * sum(components.values()) / len(components), 2)
    return {
        "enabled": True,
        "schema": profile.schema,
        "strength": round(application.strength, 3),
        "privacy_mode": "aggregate_only",
        "source_sha256": profile.source_sha256,
        "reference": profile.to_dict(),
        "application": application.decision_summary(),
        "achieved": {
            "effect_count": total,
            "timing_grid_alignment": round(achieved_alignment, 6),
            "median_effect_ms": achieved_median,
            "p90_effect_ms": achieved_p90,
            "shimmer_share": round(achieved_shimmer, 6),
            "fade_share": round(achieved_fade, 6),
            "fixed_share": round(achieved_fixed, 6),
        },
        "score": score,
        "score_components": {key: round(value * 100.0, 2) for key, value in components.items()},
    }


def disabled_calibration_summary() -> dict[str, Any]:
    return {
        "enabled": False,
        "privacy_mode": "aggregate_only",
        "reason": "No LMS calibration file was requested.",
    }


def iter_timeline_placements(timelines: Mapping[str, Any]) -> Iterable[tuple[int, int, str]]:
    for timeline in timelines.values():
        for entries in getattr(timeline, "layers", {}).values():
            for entry in entries:
                yield int(entry.start), int(entry.end), str(entry.effect_name)
