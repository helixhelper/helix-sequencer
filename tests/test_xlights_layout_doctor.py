from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from tools.xlights_layout_doctor import inspect_layout, main


def _write_layout(path: Path, *, display_as: str = "Matrix") -> None:
    root = ET.Element("xrgb")
    models = ET.SubElement(root, "models")
    ET.SubElement(
        models,
        "model",
        {
            "name": "HOUSE_MATRIX",
            "DisplayAs": display_as,
            "parm1": "32",
            "parm2": "8",
            "StringType": "RGB Nodes",
            "StartChannel": "1",
        },
    )
    ET.SubElement(root, "modelGroups")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_doctor_without_fix_reports_generic_matrix_as_blocking(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(layout)

    report = inspect_layout(layout)

    assert report["ready_for_helix"] is False
    assert report["generic_model_types"] == ["HOUSE_MATRIX"]
    assert report["normalization"] == {}


def test_doctor_fix_makes_backup_and_normalizes_layout(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(layout)

    report = inspect_layout(layout, fix=True)

    assert report["ready_for_helix"] is True
    assert report["normalization"]["changed"] == 1
    assert Path(report["backup_path"]).exists()
    model = ET.parse(layout).getroot().find("./models/model")
    assert model is not None
    assert model.attrib["DisplayAs"] == "Horiz Matrix"


def test_doctor_cli_returns_nonzero_for_blocked_layout(tmp_path: Path, capsys) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(layout)

    rc = main([str(layout)])

    assert rc == 2
    output = capsys.readouterr().out
    assert "BLOCKED:" in output
    assert "NOT READY" in output


def test_doctor_cli_fix_returns_zero_for_repaired_layout(tmp_path: Path, capsys) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(layout)

    rc = main([str(layout), "--fix", "--no-backup"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "Compatibility repairs: 1" in output
    assert "READY TO GENERATE" in output
