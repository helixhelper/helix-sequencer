from __future__ import annotations

import json
import math
import shutil
import wave
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from core.controller_parser import build_controller_plan, write_networks_file
from core.model_parser import parse_layout
from core.xlights_layout_compat import normalize_xlights_model_types, preflight_xlights_layout
from xlights import layout_sync, xml_io


LAYOUT_FILENAME = "xlights_rgbeffects.xml"
NETWORKS_FILENAME = "xlights_networks.xml"
GENERAL_LAYER = "AUTO_Helix_Beta"
DRUMMER_LAYER = "AUTO_Helix_Drummer_V3"
SHOW_MANIFEST_SUFFIX = ".show.json"
MAX_GENERAL_EFFECTS = 1400
MIN_GENERAL_MODEL_PARTICIPATION = 2
GENERAL_MODEL_PARTICIPATION_RATIO = 0.05
MAX_REQUIRED_GENERAL_MODELS = 12

DRUMMER_MODEL = "HX_SNOWMAN_DRUMMER"
DRUMMER_PREFIX = f"{DRUMMER_MODEL}/HX_SNOWMAN_DRUMMER_"

_CHANNEL_KEYS = (
    "ChannelCount",
    "channelCount",
    "Channels",
    "channels",
    "NumChannels",
    "numChannels",
    "MaxChannels",
    "maxChannels",
    "Size",
    "size",
)


def _root_child(root: ET.Element, tag: str) -> ET.Element:
    existing = xml_io.find_root_child(root, tag)
    if existing is not None:
        return existing
    child = ET.Element(tag)
    root.append(child)
    return child


def _element_type(element: ET.Element) -> str:
    return str(element.attrib.get("type", element.attrib.get("Type", "")) or "").strip().lower()


def _element_name(element: ET.Element) -> str:
    return str(element.attrib.get("name", element.attrib.get("Name", "")) or "").strip()


def _timing_tracks(root: ET.Element) -> list[ET.Element]:
    effects = xml_io.find_root_child(root, "ElementEffects")
    if effects is None:
        return []
    return [element for element in list(effects) if _element_type(element) == "timing"]


def _timing_events(track: ET.Element) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for effect in track.iter():
        if not str(effect.tag).endswith("Effect"):
            continue
        try:
            start_ms = int(round(float(effect.attrib.get("startTime", "0") or 0)))
            end_ms = int(round(float(effect.attrib.get("endTime", str(start_ms + 100)) or (start_ms + 100))))
        except (TypeError, ValueError):
            continue
        if end_ms <= start_ms:
            end_ms = start_ms + 100
        events.append(
            {
                "label": str(effect.attrib.get("label", effect.attrib.get("name", "")) or ""),
                "start_ms": max(0, start_ms),
                "end_ms": max(start_ms + 1, end_ms),
            }
        )
    events.sort(key=lambda event: (int(event["start_ms"]), int(event["end_ms"]), str(event["label"])))
    return events


def _find_track(root: ET.Element, needle: str) -> ET.Element | None:
    wanted = needle.casefold()
    for track in _timing_tracks(root):
        if wanted in _element_name(track).casefold():
            return track
    return None


def _find_general_timing_events(root: ET.Element) -> list[dict[str, object]]:
    for needle in ("AUTO Audio Reactive", "AUTO MultiBand", "AUTO Chronoflow", "AUTO Snowman Band"):
        track = _find_track(root, needle)
        if track is not None:
            events = _timing_events(track)
            if events:
                return events
    for track in _timing_tracks(root):
        name = _element_name(track).casefold()
        if "auto" not in name or "drummer" in name:
            continue
        events = _timing_events(track)
        if events:
            return events
    return []


def _drummer_timing_events(root: ET.Element) -> list[dict[str, object]]:
    track = _find_track(root, "AUTO Drummer")
    if track is None:
        return []
    events = _timing_events(track)
    for event in events:
        label = str(event.get("label", "") or "")
        kind, sep, pose = label.partition(":")
        event["drum_type"] = (kind if sep else label or "drum_bus").strip().lower()
        event["pose"] = (pose if sep else "").strip().lower()
    return events


def _audio_duration_seconds(path: Path) -> float | None:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as stream:
                rate = int(stream.getframerate())
                frames = int(stream.getnframes())
            if rate <= 0 or frames <= 0:
                return None
            return frames / float(rate)
        except (OSError, wave.Error):
            return None

    # Mutagen is optional. When present it gives Helix a portable duration path
    # for MP3/M4A/FLAC without making beta generation depend on the package.
    try:
        from mutagen import File as mutagen_file  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        audio = mutagen_file(str(path))
        info = getattr(audio, "info", None)
        length = float(getattr(info, "length", 0.0) or 0.0)
        return length if length > 0 else None
    except Exception:
        return None


def _bind_media(root: ET.Element, audio_path: Path) -> dict[str, object]:
    head = _root_child(root, "head")
    sequence_type = head.find("sequenceType")
    if sequence_type is None:
        sequence_type = ET.SubElement(head, "sequenceType")
    sequence_type.text = "Media"

    media = head.find("mediaFile")
    if media is None:
        media = ET.SubElement(head, "mediaFile")
    # The finalizer copies media beside the XSQ. A relative reference keeps the
    # show portable if the folder is moved to another machine or directory.
    media.text = audio_path.name

    duration = _audio_duration_seconds(audio_path)
    if duration is not None:
        duration_el = head.find("sequenceDuration")
        if duration_el is None:
            duration_el = ET.SubElement(head, "sequenceDuration")
        duration_el.text = f"{duration:.3f}"

    return {
        "media_file": audio_path.name,
        "media_resolved_path": str(audio_path.resolve()),
        "media_exists": audio_path.exists(),
        "sequence_duration": str(head.findtext("sequenceDuration", default="") or "").strip(),
    }


def _layout_root_model_names(layout_path: Path) -> list[str]:
    root = ET.parse(layout_path).getroot()
    models = root.find("models")
    if models is None:
        return []
    return [
        str(model.attrib.get("name", "") or "").strip()
        for model in list(models)
        if str(model.attrib.get("name", "") or "").strip()
    ]


def _positive_int(attrs: dict[str, str], *keys: str) -> int:
    for key in keys:
        raw = str(attrs.get(key, "") or "").strip()
        if not raw:
            continue
        try:
            value = int(round(float(raw)))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def _model_channel_span(model) -> int:
    raw = dict(getattr(model, "raw_attrs", {}) or {})
    explicit = _positive_int(raw, *_CHANNEL_KEYS)
    if explicit > 0:
        return explicit
    pixels = max(1, int(getattr(model, "total_pixels", 1) or 1))
    if bool(getattr(model, "is_rgb_capable", lambda: False)()):
        return pixels * 3
    return pixels


def _ranges_overlap(allocations: list[dict[str, object]]) -> int:
    ordered = sorted(
        allocations,
        key=lambda item: (int(item["start_channel"]), int(item["end_channel"]), str(item["model"])),
    )
    overlaps = 0
    previous: dict[str, object] | None = None
    for allocation in ordered:
        if previous is not None and int(allocation["start_channel"]) <= int(previous["end_channel"]):
            overlaps += 1
            if int(allocation["end_channel"]) > int(previous["end_channel"]):
                previous = allocation
        else:
            previous = allocation
    return overlaps


def normalize_preview_channels(layout_path: Path) -> dict[str, object]:
    """Make preview channel addressing deterministic without destroying good data.

    Compact, positive, non-overlapping absolute channel assignments are preserved.
    Sparse placeholder ranges and unresolved/dynamic assignments are replaced with
    sequential absolute channels. Channel span is based on the parsed model's
    StringType/NumChannels rather than assuming every node consumes three channels.
    """

    layout_path = Path(layout_path)
    parsed = parse_layout(layout_path)
    tree = ET.parse(layout_path)
    root = tree.getroot()
    models_el = root.find("models")
    if models_el is None:
        raise RuntimeError(f"Layout has no <models> section: {layout_path}")

    model_rows: list[tuple[ET.Element, object, int]] = []
    sequential_total = 0
    existing: list[dict[str, object]] = []
    existing_is_numeric = True
    for model_el in list(models_el):
        name = str(model_el.attrib.get("name", "") or "").strip()
        if not name:
            continue
        model = parsed.models.get(name)
        span = _model_channel_span(model) if model is not None else 1
        sequential_total += span
        model_rows.append((model_el, model, span))
        start = getattr(model, "start_channel", None) if model is not None else None
        if start is None or int(start) <= 0:
            existing_is_numeric = False
            continue
        start_int = int(start)
        existing.append(
            {
                "model": name,
                "start_channel": start_int,
                "end_channel": start_int + span - 1,
                "channels": span,
            }
        )

    existing_overlap_count = _ranges_overlap(existing) if existing_is_numeric and len(existing) == len(model_rows) else 0
    max_existing_end = max((int(item["end_channel"]) for item in existing), default=0)
    compact_limit = max(sequential_total * 4, sequential_total + 4096)
    preserve_existing = (
        existing_is_numeric
        and len(existing) == len(model_rows)
        and existing_overlap_count == 0
        and max_existing_end <= compact_limit
    )

    if preserve_existing:
        return {
            "models": len(existing),
            "channel_count": max_existing_end,
            "overlap_count": 0,
            "allocations": existing,
            "preserved_existing": True,
            "rewritten": False,
        }

    cursor = 1
    allocations: list[dict[str, object]] = []
    for model_el, _model, span in model_rows:
        name = str(model_el.attrib.get("name", "") or "").strip()
        start = cursor
        end = start + span - 1
        model_el.attrib["StartChannel"] = str(start)
        allocations.append(
            {
                "model": name,
                "start_channel": start,
                "end_channel": end,
                "channels": span,
            }
        )
        cursor = end + 1

    ET.indent(tree, space="  ")
    tree.write(layout_path, encoding="utf-8", xml_declaration=True)
    return {
        "models": len(allocations),
        "channel_count": max(0, cursor - 1),
        "overlap_count": 0,
        "allocations": allocations,
        "preserved_existing": False,
        "rewritten": True,
    }


def _copy_show_inputs(xsq_path: Path, *, layout_path: Path, audio_path: Path) -> dict[str, object]:
    show_dir = xsq_path.parent
    show_dir.mkdir(parents=True, exist_ok=True)

    copied_layout = show_dir / LAYOUT_FILENAME
    if layout_path.resolve() != copied_layout.resolve(strict=False):
        shutil.copy2(layout_path, copied_layout)

    normalization = normalize_xlights_model_types(copied_layout)
    channels = normalize_preview_channels(copied_layout)
    preflight = preflight_xlights_layout(copied_layout)
    if not bool(preflight.get("ok")):
        errors = "; ".join(str(item) for item in list(preflight.get("errors", []) or []))
        raise RuntimeError(f"xLights layout preflight failed for {copied_layout}: {errors}")

    copied_audio = show_dir / audio_path.name
    if audio_path.resolve() != copied_audio.resolve(strict=False):
        shutil.copy2(audio_path, copied_audio)

    plan = build_controller_plan(copied_layout, padding=50)
    networks = write_networks_file(plan, show_dir / NETWORKS_FILENAME)

    return {
        "show_dir": show_dir,
        "layout_path": copied_layout,
        "audio_path": copied_audio,
        "networks_path": networks,
        "channels": channels,
        "controller": plan.to_dict(),
        "model_type_normalization": normalization,
        "layout_preflight": preflight,
    }


def _model_effect_rows(root: ET.Element) -> list[ET.Element]:
    effects = xml_io.find_root_child(root, "ElementEffects")
    if effects is None:
        return []
    return [element for element in list(effects) if _element_type(element) == "model"]


def _model_effect_counts(root: ET.Element) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in _model_effect_rows(root):
        name = _element_name(row)
        if not name:
            continue
        counts[name] = sum(1 for effect in row.iter() if str(effect.tag).endswith("Effect"))
    return counts


def _count_model_effects(root: ET.Element) -> tuple[int, int]:
    counts = _model_effect_counts(root)
    return sum(counts.values()), sum(1 for count in counts.values() if count > 0)


def _required_general_model_count(model_count: int) -> int:
    if model_count <= 0:
        return 0
    if model_count == 1:
        return 1
    ratio_target = int(math.ceil(model_count * GENERAL_MODEL_PARTICIPATION_RATIO))
    return min(model_count, MAX_REQUIRED_GENERAL_MODELS, max(MIN_GENERAL_MODEL_PARTICIPATION, ratio_target))


def _root_models_with_effects(root: ET.Element, root_models: list[str]) -> set[str]:
    counts = _model_effect_counts(root)
    return {name for name in root_models if int(counts.get(name, 0)) > 0}


def _safe_effect(
    xsq,
    *,
    target: str,
    start_ms: int,
    end_ms: int,
    layer_name: str,
) -> bool:
    row = xsq.elements.get(target)
    if row is None:
        return False
    layer = xml_io.ensure_layer(row, layer_name)
    start = max(0, int(start_ms))
    end = max(start + 70, min(int(end_ms), start + 650))
    effect = xml_io.add_effect(layer, start, end, "On", xsq.on_tpl)
    effect.attrib.setdefault("ref", "0")
    effect.attrib.setdefault("palette", "0")
    return True


def _materialize_general_effects(xsq, layout_path: Path) -> int:
    current, _models_with_effects = _count_model_effects(xsq.root)
    root_models = [name for name in _layout_root_model_names(layout_path) if name != DRUMMER_MODEL]
    required = _required_general_model_count(len(root_models))
    active = _root_models_with_effects(xsq.root, root_models)
    if current > 0 and len(active) >= required:
        return 0

    events = _find_general_timing_events(xsq.root)
    if not events:
        return 0
    if not root_models:
        return 0

    # Fill currently dark root models first; once minimum participation is met,
    # round-robin through the whole layout so the fallback remains visually broad.
    inactive = [name for name in root_models if name not in active]
    target_order = inactive + [name for name in root_models if name in active]
    stride = max(1, len(events) // MAX_GENERAL_EFFECTS)
    selected = events[::stride][:MAX_GENERAL_EFFECTS]
    placed = 0
    for index, event in enumerate(selected):
        target = target_order[index % len(target_order)]
        if _safe_effect(
            xsq,
            target=target,
            start_ms=int(event["start_ms"]),
            end_ms=int(event["end_ms"]),
            layer_name=GENERAL_LAYER,
        ):
            placed += 1
    return placed


def _drummer_target(
    drum_type: str,
    pose: str,
    *,
    available: set[str],
    index: int,
) -> str | None:
    kind = str(drum_type or "drum_bus").strip().lower()
    pose_key = str(pose or "").strip().lower()

    if kind == "kick":
        suffix = "HIT_KICK"
    elif kind == "snare":
        suffix = "HIT_SNARE"
    elif kind in {"hihat", "hi_hat", "hat"}:
        suffix = "HIT_HIHAT"
    elif kind == "tom":
        if "right" in pose_key:
            suffix = "HIT_RIGHT_TOM"
        elif "left" in pose_key:
            suffix = "HIT_LEFT_TOM"
        else:
            suffix = "HIT_RIGHT_TOM" if index % 2 else "HIT_LEFT_TOM"
    elif kind in {"cymbal", "crash"}:
        if "both" in pose_key:
            suffix = "HIT_BOTH_CRASH"
        elif "left" in pose_key:
            suffix = "HIT_LEFT_CRASH"
        elif "right" in pose_key:
            suffix = "HIT_RIGHT_CRASH"
        else:
            suffix = "HIT_RIGHT_CRASH" if index % 2 else "HIT_LEFT_CRASH"
    else:
        suffix = "DOWNBEAT_IMPACT"

    preferred = f"{DRUMMER_PREFIX}{suffix}"
    if preferred in available:
        return preferred
    return DRUMMER_MODEL if DRUMMER_MODEL in available else None


def _materialize_drummer_effects(xsq, layout_path: Path) -> dict[str, object]:
    events = _drummer_timing_events(xsq.root)
    if not events:
        return {
            "timing_events": 0,
            "placed_effects": 0,
            "placed_by_type": {},
            "placed_keys": [],
        }

    ordered_names, _lookup = layout_sync.layout_entries_and_lookup(layout_path)
    available = set(ordered_names)
    counts: Counter[str] = Counter()
    placed_keys: list[dict[str, object]] = []

    for index, event in enumerate(events):
        drum_type = str(event.get("drum_type", "drum_bus") or "drum_bus").lower()
        pose = str(event.get("pose", "") or "")
        target = _drummer_target(drum_type, pose, available=available, index=index)
        if target is None:
            continue
        if _safe_effect(
            xsq,
            target=target,
            start_ms=int(event["start_ms"]),
            end_ms=int(event["end_ms"]),
            layer_name=DRUMMER_LAYER,
        ):
            counts[drum_type] += 1
            placed_keys.append(
                {
                    "start_ms": int(event["start_ms"]),
                    "drum_type": drum_type,
                    "target": target,
                }
            )

    return {
        "timing_events": len(events),
        "placed_effects": sum(counts.values()),
        "placed_by_type": dict(sorted(counts.items())),
        "placed_keys": placed_keys,
    }


def inspect_xsq_contract(xsq_path: Path) -> dict[str, object]:
    xsq_path = Path(xsq_path)
    root = ET.parse(xsq_path).getroot()
    display = xml_io.find_root_child(root, "DisplayElements")
    effects = xml_io.find_root_child(root, "ElementEffects")
    display_rows = list(display) if display is not None else []
    effect_rows = list(effects) if effects is not None else []

    display_model_rows = [row for row in display_rows if _element_type(row) == "model"]
    model_rows = [row for row in effect_rows if _element_type(row) == "model"]
    model_effects = 0
    models_with_effects = 0
    drummer_effects = 0
    for row in model_rows:
        count = sum(1 for effect in row.iter() if str(effect.tag).endswith("Effect"))
        model_effects += count
        if count:
            models_with_effects += 1
        if _element_name(row).startswith(DRUMMER_MODEL):
            drummer_effects += count

    drummer_events = _drummer_timing_events(root)
    media_file = str(root.findtext("./head/mediaFile", default="") or "").strip()
    media_path = Path(media_file) if media_file else None
    if media_path is not None and not media_path.is_absolute():
        media_path = xsq_path.parent / media_path
    media_exists = bool(media_path is not None and media_path.exists())
    sequence_duration = str(root.findtext("./head/sequenceDuration", default="") or "").strip()

    return {
        "display_model_rows": len(display_model_rows),
        "effect_model_rows": len(model_rows),
        "model_effects": model_effects,
        "models_with_effects": models_with_effects,
        "drummer_model_effects": drummer_effects,
        "auto_drummer_timing_events": len(drummer_events),
        "media_file": media_file,
        "media_resolved_path": str(media_path.resolve()) if media_path is not None else "",
        "media_exists": media_exists,
        "sequence_duration": sequence_duration,
    }


def _update_report(
    xsq_path: Path,
    *,
    contract: dict[str, object],
    drummer: dict[str, object],
    show: dict[str, object],
) -> None:
    report_path = xsq_path.with_name(f"{xsq_path.stem}.report.json")
    if not report_path.exists():
        return
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(payload, dict):
        return

    payload["output_contract"] = {
        **contract,
        "show_folder": str(show["show_dir"]),
        "layout_path": str(show["layout_path"]),
        "networks_path": str(show["networks_path"]),
        "channel_count": int(dict(show["channels"]).get("channel_count", 0)),
        "channel_overlap_count": int(dict(show["channels"]).get("overlap_count", 0)),
        "channel_assignments_preserved": bool(dict(show["channels"]).get("preserved_existing", False)),
        "model_type_normalization": dict(show.get("model_type_normalization", {}) or {}),
        "layout_preflight": dict(show.get("layout_preflight", {}) or {}),
    }

    drummer_payload = payload.setdefault("drummer", {})
    if isinstance(drummer_payload, dict):
        timing_events = int(drummer.get("timing_events", 0) or 0)
        placed_effects = int(drummer.get("placed_effects", 0) or 0)
        drummer_payload["placement_requests"] = timing_events
        drummer_payload["placed_effects"] = placed_effects
        drummer_payload["timing_track_events"] = timing_events
        review = drummer_payload.setdefault("review", {})
        if isinstance(review, dict):
            placed_map = {
                (int(item.get("start_ms", 0)), str(item.get("drum_type", "")).lower()): str(item.get("target", ""))
                for item in list(drummer.get("placed_keys", []) or [])
                if isinstance(item, dict)
            }
            events = list(review.get("events", []) or [])
            placed_cues = 0
            for event in events:
                if not isinstance(event, dict):
                    continue
                key = (
                    int(event.get("start_ms", 0) or 0),
                    str(event.get("drum_type", "") or "").lower(),
                )
                target = placed_map.get(key)
                if target:
                    event["placed"] = True
                    event["placement_targets"] = [target]
                    event["placed_target_count"] = 1
                    event["target_tiers"] = ["v3_pose"]
                    placed_cues += 1
            if events:
                review["placed_cues"] = placed_cues
                review["unplaced_cues"] = max(0, len(events) - placed_cues)
                review["cue_placement_ratio"] = round(placed_cues / len(events), 3)
            review["actual_effects_by_type"] = dict(drummer.get("placed_by_type", {}) or {})

    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def finalize_xsq_output(
    xsq_path: Path,
    *,
    layout_path: Path,
    audio_path: Path,
) -> dict[str, object]:
    xsq_path = Path(xsq_path)
    layout_path = Path(layout_path)
    audio_path = Path(audio_path)
    if not xsq_path.exists():
        raise RuntimeError(f"Cannot finalize missing XSQ: {xsq_path}")
    if not layout_path.exists():
        raise RuntimeError(f"Cannot finalize XSQ without layout: {layout_path}")
    if not audio_path.exists():
        raise RuntimeError(f"Cannot finalize XSQ without audio: {audio_path}")

    show = _copy_show_inputs(xsq_path, layout_path=layout_path, audio_path=audio_path)
    xsq = xml_io.load_xsq(xsq_path)
    layout_sync.sync_xsq_to_layout(xsq, Path(show["layout_path"]))
    layout_sync.ensure_master_view_models(xsq.root)
    layout_sync.normalize_display_views(xsq.root)

    _bind_media(xsq.root, Path(show["audio_path"]))
    general_added = _materialize_general_effects(xsq, Path(show["layout_path"]))
    drummer = _materialize_drummer_effects(xsq, Path(show["layout_path"]))

    ET.indent(xsq.tree, space="  ")
    xsq.tree.write(xsq_path, encoding="utf-8", xml_declaration=True)

    contract = inspect_xsq_contract(xsq_path)
    if int(contract["display_model_rows"]) <= 0 or int(contract["effect_model_rows"]) <= 0:
        raise RuntimeError(f"Generated XSQ has no xLights model rows: {xsq_path}")
    if int(contract["model_effects"]) <= 0:
        raise RuntimeError(f"Generated XSQ is timing-only; no model effects were written: {xsq_path}")

    general_root_models = [name for name in _layout_root_model_names(Path(show["layout_path"])) if name != DRUMMER_MODEL]
    root_active = _root_models_with_effects(ET.parse(xsq_path).getroot(), general_root_models)
    required_active = _required_general_model_count(len(general_root_models))
    if len(root_active) < required_active:
        raise RuntimeError(
            "Generated XSQ did not place effects across enough root models: "
            f"{len(root_active)}/{required_active} required ({len(general_root_models)} available): {xsq_path}"
        )
    if not bool(contract["media_exists"]):
        raise RuntimeError(f"Generated XSQ media reference does not resolve: {contract['media_file']}")
    if int(drummer.get("timing_events", 0) or 0) > 0 and int(contract["drummer_model_effects"]) <= 0:
        raise RuntimeError(
            "AUTO Drummer contains events but no drummer model effects were written: "
            f"{xsq_path}"
        )

    participation_ratio = round(len(root_active) / len(general_root_models), 3) if general_root_models else 1.0
    summary = {
        **contract,
        "xsq_path": str(xsq_path),
        "show_folder": str(show["show_dir"]),
        "layout_path": str(show["layout_path"]),
        "audio_path": str(show["audio_path"]),
        "networks_path": str(show["networks_path"]),
        "channel_count": int(dict(show["channels"]).get("channel_count", 0)),
        "channel_overlap_count": int(dict(show["channels"]).get("overlap_count", 0)),
        "channel_assignments_preserved": bool(dict(show["channels"]).get("preserved_existing", False)),
        "model_type_normalization": dict(show.get("model_type_normalization", {}) or {}),
        "layout_preflight": dict(show.get("layout_preflight", {}) or {}),
        "general_effects_added": general_added,
        "root_models_with_effects": len(root_active),
        "root_model_participation_required": required_active,
        "root_model_participation_ratio": participation_ratio,
        "drummer": {
            "timing_events": int(drummer.get("timing_events", 0) or 0),
            "placed_effects": int(drummer.get("placed_effects", 0) or 0),
            "placed_by_type": dict(drummer.get("placed_by_type", {}) or {}),
        },
    }
    manifest_path = xsq_path.with_name(f"{xsq_path.stem}{SHOW_MANIFEST_SUFFIX}")
    manifest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _update_report(
        xsq_path,
        contract={**contract, "root_model_participation_ratio": participation_ratio},
        drummer=drummer,
        show=show,
    )
    return summary


def _match_audio_for_output(output: Path, audios: list[Path]) -> Path | None:
    stem = output.stem
    matches = [
        candidate
        for candidate in audios
        if stem == candidate.stem
        or stem.startswith(candidate.stem + ",")
        or stem.startswith(candidate.stem + "_")
        or stem.startswith(candidate.stem + "-")
    ]
    if matches:
        return max(matches, key=lambda candidate: len(candidate.stem))
    return audios[0] if len(audios) == 1 else None


def finalize_generated_outputs(
    xsq_outputs: Iterable[Path],
    *,
    layout_path: Path,
    audio_paths: Iterable[Path],
) -> list[dict[str, object]]:
    audios = [Path(path) for path in audio_paths]
    outputs = [Path(path) for path in xsq_outputs]
    summaries: list[dict[str, object]] = []
    for output in outputs:
        audio = _match_audio_for_output(output, audios)
        if audio is None:
            raise RuntimeError(f"Cannot associate generated XSQ with requested audio: {output}")
        summaries.append(
            finalize_xsq_output(
                output,
                layout_path=Path(layout_path),
                audio_path=audio,
            )
        )
    return summaries
