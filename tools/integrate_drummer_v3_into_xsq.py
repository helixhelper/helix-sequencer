from __future__ import annotations

import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from audio.drum_classification import DRUM_STREAM_KEYS, stream_key_for_type
from audio.drum_detection_oracle import (
    APPROVED_DRUMMER_BEHAVIOR_PROFILE,
    detect_drum_event_streams_from_file_oracle,
)
from mapping.drum_mapper import (
    DRUMMER_COMPONENTS,
    flatten_drum_streams,
    map_events_to_drummer_components,
    schedule_drum_events,
)

DRUMMER_V3_MODEL = "HX_SNOWMAN_DRUMMER"
DRUMMER_TARGETS = set(DRUMMER_COMPONENTS)

KICK = "HX_SNOWMAN_DRUMMER_HIT_KICK"
SNARE = "HX_SNOWMAN_DRUMMER_HIT_SNARE"
CYMBAL_LEFT = "HX_SNOWMAN_DRUMMER_HIT_CYMBAL_LEFT"

# Recovered from the accepted 2026-09-20 placeholder-render artifact.
# These counts are for the canonical Helix Audiolights.mp3 regression song.
APPROVED_ORACLE_COUNTS = {
    "kick_events": 193,
    "snare_events": 37,
    "tom_events": 9,
    "hihat_events": 205,
    "cymbal_events": 824,
    "drum_bus_events": 47,
}
APPROVED_ORACLE_EVENT_COUNT = 1315


def _find_or_create_element_effects(root):
    return root.find("ElementEffects") or ET.SubElement(root, "ElementEffects")


def _element_map(container):
    return {
        element.get("name", ""): element
        for element in container.findall("Element")
        if element.get("name")
    }


def _layer_for(container, elements, name, layer_name):
    element = elements.get(name)
    if element is None:
        element = ET.SubElement(
            container,
            "Element",
            {"type": "model", "name": name},
        )
        elements[name] = element
    for layer in element.findall("EffectLayer"):
        if layer.get("name") == layer_name:
            return layer
    return ET.SubElement(
        element,
        "EffectLayer",
        {"name": layer_name, "visible": "1"},
    )


def _clear_layer(layer):
    for child in list(layer):
        layer.remove(child)


def _add_on(layer, start_ms, end_ms, intensity, component, source_type):
    ET.SubElement(
        layer,
        "Effect",
        {
            "name": "On",
            "startTime": str(max(0, int(start_ms))),
            "endTime": str(max(int(start_ms) + 50, int(end_ms))),
            "settings": (
                "E_CHECKBOX_OverlayBkg=0,"
                f"E_SLIDER_Brightness={max(.08, min(1., float(intensity))):.3f}"
            ),
            "palette": (
                "C_BUTTON_Palette1=#FFFFFF,"
                "C_BUTTON_Palette2=#FFFFFF,"
                "C_BUTTON_Palette3=#FFFFFF"
            ),
            "source": "HelixDrummerV3",
            "sourceModel": DRUMMER_V3_MODEL,
            "sourceComponent": component,
            "sourceDrumType": source_type,
        },
    )


def _behavior_counts(events) -> dict[str, int]:
    return {
        key: sum(
            1
            for event in events
            if stream_key_for_type(event.drum_type) == key
        )
        for key in DRUM_STREAM_KEYS
    }


def _adapt_oracle_events_to_current_components(events):
    """Apply the accepted old behavior to the newer physical kit contract.

    Typed hits use the current eight approved composites:
    * kick has no stick
    * hi-hat uses the pedal/foot composite
    * generic toms rotate left -> right -> floor
    * cymbals alternate left -> right

    The old accepted renderer also had an explicit downbeat/body-impact state
    for ambiguous drum-bus events. Preserve that *behavioral* state without
    reviving independent stick/body channels by expressing it as a simultaneous
    kick + snare + left-crash impact using existing approved composites.
    """
    component_events = map_events_to_drummer_components(
        [event for event in events if event.drum_type != "drum_bus"]
    )

    for event in events:
        if event.drum_type != "drum_bus":
            continue
        for component in (KICK, SNARE, CYMBAL_LEFT):
            component_events.append(
                {
                    "timestamp_ms": event.timestamp_ms,
                    "end_ms": event.timestamp_ms + 220,
                    "model": DRUMMER_V3_MODEL,
                    "drum_type": "downbeat_impact",
                    "component": component,
                    "intensity": round(event.velocity, 3),
                    "confidence": event.confidence,
                    "source": (
                        f"{event.source}:explicit_downbeat_impact_adapter"
                    ),
                }
            )

    return sorted(
        component_events,
        key=lambda item: (
            int(item["timestamp_ms"]),
            str(item["component"]),
        ),
    )


def inject_drummer_v3(
    base_xsq,
    output_xsq,
    audio_path,
    *,
    layer_name="AUTO_Drummer_V3",
    stem_cache_dir: Path | None = None,
):
    base_xsq = Path(base_xsq)
    output_xsq = Path(output_xsq)
    audio_path = Path(audio_path)
    if not base_xsq.exists() or not audio_path.exists():
        raise FileNotFoundError("Missing XSQ or audio input")

    cache_dir = (
        Path(stem_cache_dir)
        if stem_cache_dir is not None
        else output_xsq.parent / "stem_cache"
    )

    # Behavioral ground truth: the accepted placeholder-era drummer analyzed
    # the original mixed song directly. Do not substitute separated stems here.
    source_label = f"direct:mix:{APPROVED_DRUMMER_BEHAVIOR_PROFILE}"
    streams = detect_drum_event_streams_from_file_oracle(
        audio_path,
        source_label=source_label,
    )

    # Reproduce the accepted scheduler exactly: flatten all families,
    # including drum_bus, then use the long-standing Helix scheduling rules.
    scheduled_events = schedule_drum_events(flatten_drum_streams(streams))
    detector_counts = _behavior_counts(scheduled_events)
    component_events = _adapt_oracle_events_to_current_components(
        scheduled_events
    )

    if output_xsq.resolve() != base_xsq.resolve():
        output_xsq.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base_xsq, output_xsq)

    tree = ET.parse(output_xsq)
    root = tree.getroot()
    container = _find_or_create_element_effects(root)
    elements = _element_map(container)

    layers = {}
    for name in sorted(DRUMMER_TARGETS):
        layers[name] = _layer_for(
            container,
            elements,
            name,
            layer_name,
        )
        _clear_layer(layers[name])

    placements = 0
    for event in component_events:
        component = str(event["component"])
        if component not in DRUMMER_TARGETS:
            raise ValueError(
                f"Non-canonical drummer target emitted: {component}"
            )
        _add_on(
            layers[component],
            event["timestamp_ms"],
            event["end_ms"],
            event["intensity"],
            component,
            event["drum_type"],
        )
        placements += 1

    if layer_name not in {
        node.get("name")
        for node in root.findall("timingtrack")
    }:
        ET.SubElement(root, "timingtrack", {"name": layer_name})

    ET.indent(tree, space="  ")
    tree.write(
        output_xsq,
        encoding="utf-8",
        xml_declaration=True,
    )

    return {
        "schema": "helix.drummer_v3_xsq_integration.v4",
        "model": DRUMMER_V3_MODEL,
        "base_xsq": str(base_xsq),
        "output_xsq": str(output_xsq),
        "audio": str(audio_path),
        "layer": layer_name,
        "fallback_mode": "approved_placeholder_behavior_oracle",
        "behavior_profile": APPROVED_DRUMMER_BEHAVIOR_PROFILE,
        "behavior_detector": "single_label_onset_oracle",
        "behavior_audio_source": "original_mix",
        "behavior_event_count": len(scheduled_events),
        "stem_source": "disabled_for_behavior_oracle",
        "stem_cache_dir": str(cache_dir),
        "stems": {},
        "detector_counts": detector_counts,
        "approved_oracle_counts": dict(APPROVED_ORACLE_COUNTS),
        "approved_oracle_event_count": APPROVED_ORACLE_EVENT_COUNT,
        "event_count": len(component_events),
        "placement_count": placements,
        "downbeat_impact_count": detector_counts.get(
            "drum_bus_events",
            0,
        ),
        "component_counts": {
            component: sum(
                1
                for event in component_events
                if event["component"] == component
            )
            for component in sorted(DRUMMER_TARGETS)
        },
        "targets": sorted(DRUMMER_TARGETS),
        "target_count": len(DRUMMER_TARGETS),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_xsq", type=Path)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--layer",
        default="AUTO_Drummer_V3",
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--stem-cache", type=Path, default=None)
    args = parser.parse_args()

    report = inject_drummer_v3(
        args.base_xsq,
        args.output,
        args.audio,
        layer_name=args.layer,
        stem_cache_dir=args.stem_cache,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.report:
        args.report.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
