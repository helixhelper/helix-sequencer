from __future__ import annotations

from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

from core.model_parser import parse_layout


# xLights requires a concrete matrix orientation. Older Helix layouts sometimes
# used the generic DisplayAs="Matrix", which current xLights rejects while
# loading the show folder.
_MODEL_TYPE_ALIASES = {
    "Matrix": "Horiz Matrix",
}

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


def _matrix_replacement(model: ET.Element) -> tuple[str, bool]:
    """Return a concrete xLights matrix type and whether the choice was ambiguous.

    Generic Matrix layouts from older Helix builds generally encode their two
    principal dimensions in parm1/parm2 (or NumStrings/NodesPerString).  Prefer
    the dominant dimension when it is available.  When the dimensions do not
    distinguish an orientation, preserve the historical horizontal fallback but
    report the ambiguity so preflight/GUI diagnostics can surface it.
    """

    attrs = {str(key): str(value) for key, value in model.attrib.items()}
    horizontal = _positive_int(attrs, "MatrixWidth", "CustomWidth", "NumStrings", "parm1")
    vertical = _positive_int(attrs, "MatrixHeight", "CustomHeight", "NodesPerString", "parm2")

    hint = " ".join(
        str(attrs.get(key, "") or "")
        for key in ("Orientation", "orientation", "Direction", "direction", "Dir", "dir")
    ).casefold()
    if "vert" in hint:
        return "Vert Matrix", False
    if "horiz" in hint:
        return "Horiz Matrix", False
    if horizontal > 0 and vertical > 0:
        if vertical > horizontal:
            return "Vert Matrix", False
        if horizontal > vertical:
            return "Horiz Matrix", False
    return "Horiz Matrix", True


def normalize_xlights_model_types(layout_path: str | Path) -> dict[str, object]:
    """Rewrite known legacy xLights model-type aliases in-place.

    Returns an audit payload so callers/tests can verify what changed.  The
    function is deliberately conservative: only aliases known to be invalid in
    current xLights are rewritten; all other model attributes are preserved.
    """

    path = Path(layout_path)
    tree = ET.parse(path)
    root = tree.getroot()

    changed = 0
    matrix_aliases = 0
    matrix_horizontal = 0
    matrix_vertical = 0
    ambiguous_matrices: list[str] = []
    for model in root.findall(".//models/model"):
        display_as = str(model.attrib.get("DisplayAs") or "").strip()
        replacement = _MODEL_TYPE_ALIASES.get(display_as)
        if replacement is None:
            continue
        if display_as == "Matrix":
            matrix_aliases += 1
            replacement, ambiguous = _matrix_replacement(model)
            if replacement == "Vert Matrix":
                matrix_vertical += 1
            else:
                matrix_horizontal += 1
            if ambiguous:
                ambiguous_matrices.append(str(model.attrib.get("name", "") or "<unnamed>"))
        model.attrib["DisplayAs"] = replacement
        changed += 1

    if changed:
        ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)

    return {
        "changed": changed,
        "matrix_aliases": matrix_aliases,
        "matrix_horizontal": matrix_horizontal,
        "matrix_vertical": matrix_vertical,
        "ambiguous_matrices": ambiguous_matrices,
    }


def _model_channel_span(model) -> int:
    raw_num_channels = _positive_int(dict(getattr(model, "raw_attrs", {}) or {}), *_CHANNEL_KEYS)
    if raw_num_channels > 0:
        return raw_num_channels
    pixels = max(1, int(getattr(model, "total_pixels", 1) or 1))
    if bool(getattr(model, "is_rgb_capable", lambda: False)()):
        return pixels * 3
    return pixels


def _layout_names(root: ET.Element) -> tuple[list[str], list[str], set[str]]:
    model_names: list[str] = []
    all_targets: set[str] = set()
    models_el = root.find("models")
    if models_el is not None:
        for model in list(models_el):
            name = str(model.attrib.get("name", "") or "").strip()
            if name:
                model_names.append(name)
                all_targets.add(name)
                for submodel in model.findall("./subModel"):
                    sub_name = str(submodel.attrib.get("name", "") or "").strip()
                    if sub_name:
                        all_targets.add(f"{name}/{sub_name}")

    group_names: list[str] = []
    groups_el = root.find("modelGroups")
    if groups_el is not None:
        for group in list(groups_el):
            name = str(group.attrib.get("name", "") or "").strip()
            if name:
                group_names.append(name)
                all_targets.add(name)
    return model_names, group_names, all_targets


def preflight_xlights_layout(layout_path: str | Path) -> dict[str, object]:
    """Validate the parts of an xLights layout Helix can verify deterministically.

    This is intentionally stricter about structural problems Helix can prove and
    intentionally tolerant of xLights model types it does not own.  Unknown model
    types are therefore not rejected merely because Helix has not catalogued
    them.  The returned payload is suitable for a GUI "Layout Doctor" panel.
    """

    path = Path(layout_path)
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return {
            "ok": False,
            "models": 0,
            "groups": 0,
            "errors": [f"layout does not exist: {path}"],
            "warnings": [],
            "duplicate_names": [],
            "unresolved_group_refs": [],
            "channel_overlap_count": 0,
            "generic_model_types": [],
        }

    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return {
            "ok": False,
            "models": 0,
            "groups": 0,
            "errors": [f"layout XML parse failed: {exc}"],
            "warnings": [],
            "duplicate_names": [],
            "unresolved_group_refs": [],
            "channel_overlap_count": 0,
            "generic_model_types": [],
        }

    models_el = root.find("models")
    if models_el is None:
        errors.append("layout has no <models> section")
        model_elements: list[ET.Element] = []
    else:
        model_elements = list(models_el)

    model_names, group_names, all_targets = _layout_names(root)
    blank_model_count = sum(1 for model in model_elements if not str(model.attrib.get("name", "") or "").strip())
    if blank_model_count:
        errors.append(f"{blank_model_count} model(s) have no name")

    counts = Counter(model_names + group_names)
    duplicate_names = sorted(name for name, count in counts.items() if count > 1)
    if duplicate_names:
        errors.append("duplicate model/group names: " + ", ".join(duplicate_names))

    generic_model_types = sorted(
        str(model.attrib.get("name", "") or "<unnamed>")
        for model in model_elements
        if str(model.attrib.get("DisplayAs", "") or "").strip() in _MODEL_TYPE_ALIASES
    )
    if generic_model_types:
        errors.append("unsupported generic model types remain: " + ", ".join(generic_model_types))

    for model in model_elements:
        name = str(model.attrib.get("name", "") or "<unnamed>").strip()
        if not str(model.attrib.get("DisplayAs", "") or "").strip():
            errors.append(f"model {name} has no DisplayAs type")

    unresolved_group_refs: list[str] = []
    groups_el = root.find("modelGroups")
    if groups_el is not None:
        for group in list(groups_el):
            group_name = str(group.attrib.get("name", "") or "<unnamed-group>").strip()
            raw_members = str(group.attrib.get("models", group.attrib.get("Models", "")) or "")
            for member in (part.strip() for part in raw_members.split(",")):
                if not member or member in all_targets:
                    continue
                unresolved_group_refs.append(f"{group_name}:{member}")
    unresolved_group_refs.sort()
    if unresolved_group_refs:
        errors.append("unresolved model-group references: " + ", ".join(unresolved_group_refs))

    overlap_pairs: list[str] = []
    try:
        parsed = parse_layout(path)
        ranges: list[tuple[int, int, str]] = []
        for name in model_names:
            model = parsed.models.get(name)
            if model is None:
                continue
            start = getattr(model, "start_channel", None)
            if start is None:
                warnings.append(f"model {name} has a non-numeric or unresolved StartChannel")
                continue
            start_int = int(start)
            if start_int <= 0:
                errors.append(f"model {name} has invalid StartChannel={start_int}")
                continue
            end = start_int + _model_channel_span(model) - 1
            ranges.append((start_int, end, name))
        ranges.sort(key=lambda item: (item[0], item[1], item[2]))
        previous: tuple[int, int, str] | None = None
        for item in ranges:
            if previous is not None and item[0] <= previous[1]:
                overlap_pairs.append(f"{previous[2]}:{previous[0]}-{previous[1]} overlaps {item[2]}:{item[0]}-{item[1]}")
                if item[1] > previous[1]:
                    previous = item
            else:
                previous = item
    except Exception as exc:
        errors.append(f"layout model parse failed: {exc}")

    if overlap_pairs:
        errors.append("channel overlaps: " + "; ".join(overlap_pairs))

    return {
        "ok": not errors,
        "models": len(model_names),
        "groups": len(group_names),
        "errors": errors,
        "warnings": warnings,
        "duplicate_names": duplicate_names,
        "unresolved_group_refs": unresolved_group_refs,
        "channel_overlap_count": len(overlap_pairs),
        "generic_model_types": generic_model_types,
    }
