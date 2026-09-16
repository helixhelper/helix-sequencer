from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from core.xlights_layout_compat import normalize_xlights_model_types, preflight_xlights_layout


def _write_layout(path: Path, models: list[dict[str, str]], *, groups: list[dict[str, str]] | None = None) -> None:
    root = ET.Element("xrgb")
    models_el = ET.SubElement(root, "models")
    for attrs in models:
        ET.SubElement(models_el, "model", attrs)
    groups_el = ET.SubElement(root, "modelGroups")
    for attrs in groups or []:
        ET.SubElement(groups_el, "modelGroup", attrs)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_normalize_xlights_model_types_rewrites_generic_matrix(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(
        layout,
        [
            {
                "name": "HX_HOUSE_1_2_MATRIX",
                "DisplayAs": "Matrix",
                "parm1": "32",
                "parm2": "16",
                "parm3": "1",
                "StringType": "RGB Nodes",
                "StartChannel": "1",
            },
            {
                "name": "HX_ARCH",
                "DisplayAs": "Single Line",
                "parm1": "10",
                "StringType": "RGB Nodes",
                "StartChannel": "2000",
            },
        ],
    )

    audit = normalize_xlights_model_types(layout)

    assert audit["changed"] == 1
    assert audit["matrix_aliases"] == 1
    assert audit["matrix_horizontal"] == 1
    assert audit["matrix_vertical"] == 0
    assert audit["ambiguous_matrices"] == []
    output = ET.parse(layout).getroot()
    matrix = output.find(".//models/model[@name='HX_HOUSE_1_2_MATRIX']")
    arch = output.find(".//models/model[@name='HX_ARCH']")
    assert matrix is not None
    assert arch is not None
    assert matrix.attrib["DisplayAs"] == "Horiz Matrix"
    assert arch.attrib["DisplayAs"] == "Single Line"
    assert not output.findall(".//models/model[@DisplayAs='Matrix']")


def test_generic_tall_matrix_becomes_vertical(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(
        layout,
        [
            {
                "name": "TALL_MATRIX",
                "DisplayAs": "Matrix",
                "parm1": "8",
                "parm2": "32",
                "StringType": "RGB Nodes",
                "StartChannel": "1",
            }
        ],
    )

    audit = normalize_xlights_model_types(layout)

    assert audit["matrix_vertical"] == 1
    assert audit["ambiguous_matrices"] == []
    model = ET.parse(layout).getroot().find("./models/model")
    assert model is not None
    assert model.attrib["DisplayAs"] == "Vert Matrix"


def test_square_generic_matrix_reports_ambiguity_but_is_made_loadable(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(
        layout,
        [
            {
                "name": "SQUARE_MATRIX",
                "DisplayAs": "Matrix",
                "parm1": "16",
                "parm2": "16",
                "StringType": "RGB Nodes",
                "StartChannel": "1",
            }
        ],
    )

    audit = normalize_xlights_model_types(layout)

    assert audit["ambiguous_matrices"] == ["SQUARE_MATRIX"]
    model = ET.parse(layout).getroot().find("./models/model")
    assert model is not None
    assert model.attrib["DisplayAs"] == "Horiz Matrix"


def test_preflight_rejects_generic_matrix_duplicate_names_and_missing_group_member(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(
        layout,
        [
            {
                "name": "DUP",
                "DisplayAs": "Matrix",
                "parm1": "4",
                "parm2": "4",
                "StringType": "RGB Nodes",
                "StartChannel": "1",
            },
            {
                "name": "DUP",
                "DisplayAs": "Single Line",
                "parm1": "10",
                "StringType": "RGB Nodes",
                "StartChannel": "100",
            },
        ],
        groups=[{"name": "ALL", "models": "DUP,MISSING"}],
    )

    report = preflight_xlights_layout(layout)

    assert report["ok"] is False
    assert report["duplicate_names"] == ["DUP"]
    assert report["generic_model_types"] == ["DUP"]
    assert report["unresolved_group_refs"] == ["ALL:MISSING"]


def test_preflight_accepts_normalized_non_overlapping_layout(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(
        layout,
        [
            {
                "name": "MATRIX",
                "DisplayAs": "Matrix",
                "parm1": "4",
                "parm2": "2",
                "StringType": "RGB Nodes",
                "StartChannel": "1",
            },
            {
                "name": "LINE",
                "DisplayAs": "Single Line",
                "parm1": "5",
                "parm2": "1",
                "StringType": "RGB Nodes",
                "StartChannel": "25",
            },
        ],
        groups=[{"name": "ALL", "models": "MATRIX,LINE"}],
    )
    normalize_xlights_model_types(layout)

    report = preflight_xlights_layout(layout)

    assert report["ok"] is True
    assert report["models"] == 2
    assert report["groups"] == 1
    assert report["channel_overlap_count"] == 0
    assert report["generic_model_types"] == []


def test_preflight_reports_numeric_channel_overlap(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(
        layout,
        [
            {
                "name": "A",
                "DisplayAs": "Single Line",
                "parm1": "10",
                "parm2": "1",
                "StringType": "RGB Nodes",
                "StartChannel": "1",
            },
            {
                "name": "B",
                "DisplayAs": "Single Line",
                "parm1": "10",
                "parm2": "1",
                "StringType": "RGB Nodes",
                "StartChannel": "20",
            },
        ],
    )

    report = preflight_xlights_layout(layout)

    assert report["ok"] is False
    assert report["channel_overlap_count"] == 1
    assert any("channel overlaps" in error for error in report["errors"])
