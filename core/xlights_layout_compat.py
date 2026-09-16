from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET


# xLights requires a concrete matrix orientation. Older Helix layouts sometimes
# used the generic DisplayAs="Matrix", which current xLights rejects while
# loading the show folder.
_MODEL_TYPE_ALIASES = {
    "Matrix": "Horiz Matrix",
}


def normalize_xlights_model_types(layout_path: str | Path) -> dict[str, int]:
    """Rewrite known legacy xLights model-type aliases in-place.

    Returns a small audit payload so callers/tests can verify what changed.
    The function is deliberately conservative: only aliases known to be invalid
    in current xLights are rewritten; all other model attributes are preserved.
    """

    path = Path(layout_path)
    tree = ET.parse(path)
    root = tree.getroot()

    changed = 0
    matrix_aliases = 0
    for model in root.findall(".//models/model"):
        display_as = str(model.attrib.get("DisplayAs") or "").strip()
        replacement = _MODEL_TYPE_ALIASES.get(display_as)
        if replacement is None:
            continue
        model.attrib["DisplayAs"] = replacement
        changed += 1
        if display_as == "Matrix":
            matrix_aliases += 1

    if changed:
        tree.write(path, encoding="utf-8", xml_declaration=True)

    return {
        "changed": changed,
        "matrix_aliases": matrix_aliases,
    }
