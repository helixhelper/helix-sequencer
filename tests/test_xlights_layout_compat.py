from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from core.xlights_layout_compat import normalize_xlights_model_types


def test_normalize_xlights_model_types_rewrites_generic_matrix(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    root = ET.Element("xrgb")
    models = ET.SubElement(root, "models")
    ET.SubElement(
        models,
        "model",
        {
            "name": "HX_HOUSE_1_2_MATRIX",
            "DisplayAs": "Matrix",
            "parm1": "32",
            "parm2": "16",
            "parm3": "1",
            "StartChannel": "1",
        },
    )
    ET.SubElement(
        models,
        "model",
        {
            "name": "HX_ARCH",
            "DisplayAs": "Single Line",
            "parm1": "10",
            "StartChannel": "100",
        },
    )
    ET.ElementTree(root).write(layout, encoding="utf-8", xml_declaration=True)

    audit = normalize_xlights_model_types(layout)

    assert audit == {"changed": 1, "matrix_aliases": 1}
    output = ET.parse(layout).getroot()
    matrix = output.find(".//models/model[@name='HX_HOUSE_1_2_MATRIX']")
    arch = output.find(".//models/model[@name='HX_ARCH']")
    assert matrix is not None
    assert arch is not None
    assert matrix.attrib["DisplayAs"] == "Horiz Matrix"
    assert arch.attrib["DisplayAs"] == "Single Line"
    assert not output.findall(".//models/model[@DisplayAs='Matrix']")
