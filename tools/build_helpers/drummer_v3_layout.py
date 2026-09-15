from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_XMODEL = ROOT / "fixtures" / "band_geometry" / "models" / "HX_SNOWMAN_DRUMMER_V3.xmodel"
SOURCE_MODEL = "HX_SNOWMAN_DRUMMER_V3"
CANONICAL_MODEL = "HX_SNOWMAN_DRUMMER"
SOURCE_PREFIX = f"{SOURCE_MODEL}_"
CANONICAL_PREFIX = f"{CANONICAL_MODEL}_"


def _canonical_submodel_name(name: str) -> str:
    value = str(name or "").strip()
    if value.startswith(SOURCE_PREFIX):
        return CANONICAL_PREFIX + value[len(SOURCE_PREFIX):]
    return value


def install_drummer_v3_layout_model(
    layout_path: str | Path,
    *,
    xmodel_path: str | Path = DEFAULT_XMODEL,
) -> dict[str, object]:
    """Install the authored V3 xmodel under the canonical runtime model name."""

    target_path = Path(layout_path)
    source_path = Path(xmodel_path)
    source_root = ET.parse(source_path).getroot()
    if source_root.tag != "custommodel" or source_root.attrib.get("name") != SOURCE_MODEL:
        raise ValueError(f"Unexpected Drummer V3 xmodel: {source_path}")
    if not source_root.attrib.get("CustomModel"):
        raise ValueError(f"Drummer V3 xmodel has no CustomModel geometry: {source_path}")

    tree = ET.parse(target_path)
    root = tree.getroot()
    models_el = root.find("models")
    if models_el is None:
        models_el = ET.SubElement(root, "models")

    previous: ET.Element | None = None
    previous_index = len(list(models_el))
    for index, model in enumerate(list(models_el)):
        if model.attrib.get("name") in {CANONICAL_MODEL, SOURCE_MODEL}:
            if model.attrib.get("name") == CANONICAL_MODEL:
                previous = model
                previous_index = index
            models_el.remove(model)

    attrs = dict(source_root.attrib)
    attrs["name"] = CANONICAL_MODEL
    attrs["DisplayAs"] = "Custom"
    attrs["HelixImplementationState"] = "drummer_v3_beta"
    attrs["HelixSourceModel"] = SOURCE_MODEL
    attrs.pop("CustomBkgImage", None)
    for key, fallback in (
        ("WorldPosX", "345.000"),
        ("WorldPosY", "-58.000"),
        ("WorldPosZ", "12.000"),
        ("StartChannel", "900000"),
    ):
        attrs[key] = (previous.attrib.get(key) if previous is not None else None) or fallback

    model = ET.Element("model", attrs)
    source_submodels = source_root.findall("./subModels/subModel")
    for source_submodel in source_submodels:
        submodel = deepcopy(source_submodel)
        source_name = str(submodel.attrib.get("name", "") or "")
        submodel.attrib["name"] = _canonical_submodel_name(source_name)
        submodel.attrib["HelixSourceSubmodel"] = source_name
        model.append(submodel)
    models_el.insert(min(previous_index, len(list(models_el))), model)

    groups_el = root.find("modelGroups")
    if groups_el is not None:
        for group in groups_el.findall("./modelGroup"):
            members = [value.strip() for value in str(group.attrib.get("models", "")).split(",") if value.strip()]
            normalized = [CANONICAL_MODEL if value == SOURCE_MODEL else value for value in members]
            if group.attrib.get("name") in {"HX_SNOWMAN_BAND", "HX_SNOWMAN_INSTRUMENTS", "HX_SNOWMAN_DRUMS"}:
                if CANONICAL_MODEL not in normalized:
                    normalized.append(CANONICAL_MODEL)
            group.attrib["models"] = ",".join(dict.fromkeys(normalized))

    ET.indent(tree, space="  ")
    tree.write(target_path, encoding="utf-8", xml_declaration=True)
    return {
        "schema": "helix.drummer_v3_layout_install.v1",
        "layout_path": str(target_path),
        "source_xmodel": str(source_path),
        "source_model": SOURCE_MODEL,
        "layout_model": CANONICAL_MODEL,
        "implementation_state": "drummer_v3_beta",
        "submodel_count": len(source_submodels),
        "node_count": int(source_root.attrib.get("HelixNodeCount", "0") or 0),
        "pose_submodels": [
            _canonical_submodel_name(str(item.attrib.get("name", "") or ""))
            for item in source_submodels
            if "_HIT_" in str(item.attrib.get("name", "")) or str(item.attrib.get("name", "")).endswith("_DOWNBEAT_IMPACT")
        ],
    }
