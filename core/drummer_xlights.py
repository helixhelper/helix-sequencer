from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


CANONICAL_DRUMMER_MODEL = "HX_SNOWMAN_DRUMMER"
SOURCE_DRUMMER_V3_MODEL = "HX_SNOWMAN_DRUMMER_V3"
SOURCE_PREFIX = f"{SOURCE_DRUMMER_V3_MODEL}_"
LAYOUT_PREFIX = f"{CANONICAL_DRUMMER_MODEL}_"


@dataclass(frozen=True)
class DrummerPlacement:
    target: str
    start_ms: int
    end_ms: int
    label: str
    effect: str
    stem: str
    pose: str
    drum_type: str
    target_tier: str
    intensity: float
    confidence: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _layout_submodel_name(name: str) -> str:
    value = str(name or "").strip()
    if value.startswith(SOURCE_PREFIX):
        return LAYOUT_PREFIX + value[len(SOURCE_PREFIX):]
    return value


def _qualify(model: str, submodel: str) -> str:
    value = str(submodel or "").strip()
    if not value:
        return ""
    return value if "/" in value else f"{model}/{value}"


def _fallback_submodels(cue: Mapping[str, Any]) -> list[str]:
    drum_type = str(cue.get("kind", "drum_bus") or "drum_bus").lower()
    pose = str(cue.get("pose", "") or "").lower()
    suffixes: list[str]
    if drum_type == "kick":
        suffixes = ["KICK", "KICK_RIM"]
    elif drum_type == "snare":
        suffixes = ["SNARE", "SNARE_RIM", "LEFT_STICK"]
    elif drum_type == "hihat":
        suffixes = ["HI_HAT", "RIGHT_STICK"]
    elif drum_type == "tom":
        side = "RIGHT" if "right" in pose else "LEFT"
        suffixes = [f"TOM_{side}", f"{side}_STICK"]
    elif drum_type == "cymbal":
        if "both" in pose:
            suffixes = ["CYMBAL_LEFT", "CYMBAL_RIGHT", "LEFT_STICK", "RIGHT_STICK"]
        elif "left" in pose:
            suffixes = ["CYMBAL_LEFT", "LEFT_STICK"]
        else:
            suffixes = ["CYMBAL_RIGHT", "RIGHT_STICK"]
    else:
        suffixes = ["KICK", "SNARE", "CYMBAL_LEFT", "CYMBAL_RIGHT"]
    return [f"{LAYOUT_PREFIX}{suffix}" for suffix in suffixes]


def _first_available_group(
    groups: Iterable[tuple[str, Iterable[str]]],
    available: Mapping[str, str],
) -> tuple[list[str], str]:
    for tier, candidates in groups:
        selected: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            actual = available.get(str(candidate).casefold())
            if actual and actual not in seen:
                selected.append(actual)
                seen.add(actual)
        if selected:
            return selected, tier
    return [], "missing"


def resolve_drummer_targets(
    cue: Mapping[str, Any],
    *,
    available_targets: Iterable[str],
) -> tuple[list[str], str]:
    """Resolve a pose cue to concrete XSQ rows, preferring authored V3 composites."""

    available = {str(name).casefold(): str(name) for name in available_targets if str(name).strip()}
    layout_model = str(cue.get("xlights_model", CANONICAL_DRUMMER_MODEL) or CANONICAL_DRUMMER_MODEL)
    source_model = str(cue.get("source_model", SOURCE_DRUMMER_V3_MODEL) or SOURCE_DRUMMER_V3_MODEL)
    layout_submodels = [
        _layout_submodel_name(str(name))
        for name in list(cue.get("xlights_submodels", []) or [])
        if str(name).strip()
    ]
    source_submodels = [
        str(name)
        for name in list(cue.get("source_submodels", []) or [])
        if str(name).strip()
    ]
    if not layout_submodels:
        layout_submodels = [_layout_submodel_name(name) for name in source_submodels]

    fallback = _fallback_submodels(cue)
    groups = [
        ("v3_pose", [_qualify(layout_model, name) for name in layout_submodels]),
        ("v3_compat", [_qualify(layout_model, name) for name in source_submodels]),
        ("v3_side_by_side", [_qualify(source_model, name) for name in source_submodels]),
        ("v2_parts", [_qualify(CANONICAL_DRUMMER_MODEL, name) for name in fallback]),
        ("root_model", [layout_model, source_model, CANONICAL_DRUMMER_MODEL]),
    ]
    return _first_available_group(groups, available)


def translate_drummer_cues(
    cues: Iterable[Mapping[str, Any]],
    *,
    available_targets: Iterable[str],
    limit: int = 2400,
) -> list[dict[str, object]]:
    """Translate analyzed drummer cues into safe xLights On placements."""

    available = list(available_targets)
    placements: list[DrummerPlacement] = []
    seen: set[tuple[str, int, int, str]] = set()
    for cue in sorted(cues, key=lambda item: (int(item.get("start_ms", 0) or 0), str(item.get("kind", "")))):
        if len(placements) >= max(0, int(limit)):
            break
        start_ms = max(0, int(cue.get("start_ms", 0) or 0))
        end_ms = max(start_ms + 70, int(cue.get("end_ms", start_ms + 140) or (start_ms + 140)))
        drum_type = str(cue.get("kind", "drum_bus") or "drum_bus")
        pose = str(cue.get("pose", f"{drum_type}_hit") or f"{drum_type}_hit")
        targets, target_tier = resolve_drummer_targets(cue, available_targets=available)
        for target in targets:
            if len(placements) >= max(0, int(limit)):
                break
            key = (target, start_ms, end_ms, pose)
            if key in seen:
                continue
            seen.add(key)
            placements.append(
                DrummerPlacement(
                    target=target,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    label=f"drummer_{pose}_{drum_type}",
                    effect="On",
                    stem="drums",
                    pose=pose,
                    drum_type=drum_type,
                    target_tier=target_tier,
                    intensity=round(float(cue.get("velocity", 0.65) or 0.65), 3),
                    confidence=round(float(cue.get("confidence", 0.0) or 0.0), 3),
                )
            )
    return [placement.as_dict() for placement in placements]


def build_timing_track(
    placements: Iterable[Mapping[str, Any]],
    *,
    limit: int = 2400,
) -> list[tuple[str, int, int]]:
    track = [
        (
            f"{placement.get('drum_type', 'hit')}:{placement.get('pose', 'pose')}",
            int(placement.get("start_ms", 0) or 0),
            int(placement.get("end_ms", 0) or 0),
        )
        for placement in placements
        if int(placement.get("end_ms", 0) or 0) > int(placement.get("start_ms", 0) or 0)
    ]
    track.sort(key=lambda item: (item[1], item[2], item[0]))
    return track[: max(0, int(limit))]
