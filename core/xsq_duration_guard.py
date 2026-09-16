from __future__ import annotations

import json
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


SHOW_MANIFEST_SUFFIX = ".show.json"
REPORT_SUFFIX = ".report.json"
DRUMMER_MODEL_PREFIX = "HX_SNOWMAN_DRUMMER"


def _positive_duration_ms(value: str | None) -> int | None:
    try:
        seconds = float(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return max(1, int(round(seconds * 1000.0)))


def _wav_duration_ms(path: Path) -> int | None:
    if path.suffix.lower() != ".wav":
        return None
    try:
        with wave.open(str(path), "rb") as stream:
            rate = int(stream.getframerate())
            frames = int(stream.getnframes())
    except (OSError, wave.Error):
        return None
    if rate <= 0 or frames <= 0:
        return None
    return max(1, int(round(frames * 1000.0 / rate)))


def _media_duration_ms(xsq_path: Path, root: ET.Element) -> int | None:
    media_file = str(root.findtext("./head/mediaFile", default="") or "").strip()
    if not media_file:
        return None
    media_path = Path(media_file)
    if not media_path.is_absolute():
        media_path = xsq_path.parent / media_path
    if not media_path.is_file():
        return None

    wav_duration = _wav_duration_ms(media_path)
    if wav_duration is not None:
        return wav_duration

    # Mutagen is intentionally optional in the packaged beta. Use it when the
    # source environment already provides it, otherwise fall back to the XSQ
    # sequenceDuration written by the normal finalization path.
    try:
        from mutagen import File as mutagen_file  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        audio = mutagen_file(str(media_path))
        info = getattr(audio, "info", None)
        seconds = float(getattr(info, "length", 0.0) or 0.0)
    except Exception:
        return None
    if seconds <= 0:
        return None
    return max(1, int(round(seconds * 1000.0)))


def _resolved_duration_ms(xsq_path: Path, root: ET.Element) -> tuple[int, str]:
    media_duration = _media_duration_ms(xsq_path, root)
    if media_duration is not None:
        return media_duration, "media"
    sequence_duration = _positive_duration_ms(root.findtext("./head/sequenceDuration"))
    if sequence_duration is not None:
        return sequence_duration, "sequenceDuration"
    raise RuntimeError(f"Cannot determine finalized sequence duration for XSQ: {xsq_path}")


def _effect_times(effect: ET.Element) -> tuple[int, int] | None:
    try:
        start = int(round(float(effect.attrib.get("startTime", "0") or 0)))
        end = int(round(float(effect.attrib.get("endTime", "0") or 0)))
    except (TypeError, ValueError):
        return None
    return start, end


def _remaining_out_of_range(root: ET.Element, duration_ms: int) -> int:
    count = 0
    effects_root = root.find("./ElementEffects")
    if effects_root is None:
        return 0
    for effect in effects_root.findall(".//Effect"):
        times = _effect_times(effect)
        if times is None:
            continue
        start, end = times
        if start >= duration_ms or end > duration_ms:
            count += 1
    return count


def _model_effect_counts(root: ET.Element) -> dict[str, int]:
    effects_root = root.find("./ElementEffects")
    model_effects = 0
    drummer_effects = 0
    models_with_effects = 0
    if effects_root is None:
        return {
            "model_effects": 0,
            "models_with_effects": 0,
            "drummer_model_effects": 0,
        }
    for element in effects_root.findall("Element"):
        kind = str(element.attrib.get("type", "") or "").strip().lower()
        if kind != "model":
            continue
        count = len(element.findall(".//Effect"))
        if count:
            models_with_effects += 1
        model_effects += count
        name = str(element.attrib.get("name", "") or "").strip()
        if name.startswith(DRUMMER_MODEL_PREFIX):
            drummer_effects += count
    return {
        "model_effects": model_effects,
        "models_with_effects": models_with_effects,
        "drummer_model_effects": drummer_effects,
    }


def _update_json_metadata(path: Path, key: str, summary: dict[str, Any]) -> None:
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(payload, dict):
        return

    current_counts = {
        "model_effects": int(summary.get("model_effects_after", 0) or 0),
        "models_with_effects": int(summary.get("models_with_effects_after", 0) or 0),
        "drummer_model_effects": int(summary.get("drummer_model_effects_after", 0) or 0),
    }
    if key == "output_contract":
        nested = payload.setdefault("output_contract", {})
        if not isinstance(nested, dict):
            return
        nested.update(current_counts)
        nested["duration_normalization"] = summary
    else:
        payload.update(current_counts)
        payload["duration_normalization"] = summary
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def normalize_xsq_duration(xsq_path: Path) -> dict[str, Any]:
    """Remove or clip effects that extend past the finalized song duration.

    Legacy templates can carry timing marks far beyond the selected song. Those
    marks must not extend a generated sequence or diagnostic preview. The media
    duration is authoritative when it can be read; otherwise the finalized XSQ
    ``sequenceDuration`` is used.

    If a sequence had model effects before normalization, trimming is not allowed
    to silently turn it back into a timing-only sequence. That protects the beta
    output contract even though duration cleanup happens after materialization.
    """

    xsq_path = Path(xsq_path)
    tree = ET.parse(xsq_path)
    root = tree.getroot()
    duration_ms, duration_source = _resolved_duration_ms(xsq_path, root)
    effects_root = root.find("./ElementEffects")
    before_counts = _model_effect_counts(root)

    removed = 0
    clipped = 0
    removed_timing = 0
    removed_model = 0
    clipped_timing = 0
    clipped_model = 0
    tracks_touched: set[str] = set()

    if effects_root is not None:
        for element in effects_root.findall("Element"):
            kind = str(element.attrib.get("type", "") or "").strip().lower()
            track_name = str(element.attrib.get("name", "") or "").strip()
            is_timing = kind == "timing"
            for layer in element.findall(".//EffectLayer"):
                for effect in list(layer.findall("Effect")):
                    times = _effect_times(effect)
                    if times is None:
                        continue
                    start, end = times
                    if start >= duration_ms:
                        layer.remove(effect)
                        removed += 1
                        removed_timing += int(is_timing)
                        removed_model += int(not is_timing)
                        if track_name:
                            tracks_touched.add(track_name)
                        continue
                    if end > duration_ms:
                        effect.set("endTime", str(duration_ms))
                        clipped += 1
                        clipped_timing += int(is_timing)
                        clipped_model += int(not is_timing)
                        if track_name:
                            tracks_touched.add(track_name)

    remaining = _remaining_out_of_range(root, duration_ms)
    if remaining:
        raise RuntimeError(
            f"XSQ duration normalization left {remaining} effect(s) past {duration_ms} ms: {xsq_path}"
        )

    after_counts = _model_effect_counts(root)
    if before_counts["model_effects"] > 0 and after_counts["model_effects"] <= 0:
        raise RuntimeError(
            "XSQ duration normalization removed every model effect; refusing timing-only output: "
            f"{xsq_path}"
        )

    if removed or clipped:
        ET.indent(tree, space="  ")
        tree.write(xsq_path, encoding="utf-8", xml_declaration=True)

    summary: dict[str, Any] = {
        "duration_ms": duration_ms,
        "duration_source": duration_source,
        "removed_effects": removed,
        "clipped_effects": clipped,
        "removed_timing_effects": removed_timing,
        "removed_model_effects": removed_model,
        "clipped_timing_effects": clipped_timing,
        "clipped_model_effects": clipped_model,
        "tracks_touched": sorted(tracks_touched),
        "remaining_out_of_range_effects": remaining,
        "model_effects_before": before_counts["model_effects"],
        "model_effects_after": after_counts["model_effects"],
        "models_with_effects_after": after_counts["models_with_effects"],
        "drummer_model_effects_after": after_counts["drummer_model_effects"],
    }

    _update_json_metadata(
        xsq_path.with_name(f"{xsq_path.stem}{SHOW_MANIFEST_SUFFIX}"),
        "show_manifest",
        summary,
    )
    _update_json_metadata(
        xsq_path.with_name(f"{xsq_path.stem}{REPORT_SUFFIX}"),
        "output_contract",
        summary,
    )
    return summary
