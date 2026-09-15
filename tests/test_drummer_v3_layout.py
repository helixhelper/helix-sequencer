from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from tools.build_helpers.drummer_v3_layout import install_drummer_v3_layout_model


def test_v3_xmodel_installs_under_canonical_runtime_name(tmp_path: Path) -> None:
    layout_path = tmp_path / "xlights_rgbeffects.xml"
    layout_path.write_text(
        """
<xrgb>
  <models>
    <model name="HX_SNOWMAN_DRUMMER" DisplayAs="Custom" StartChannel="12345"
           WorldPosX="1" WorldPosY="2" WorldPosZ="3" />
  </models>
  <modelGroups>
    <modelGroup name="HX_SNOWMAN_BAND" models="HX_SNOWMAN_DRUMMER" />
  </modelGroups>
</xrgb>
""".strip(),
        encoding="utf-8",
    )

    result = install_drummer_v3_layout_model(layout_path)
    root = ET.parse(layout_path).getroot()
    models = root.findall("./models/model")
    drummer = root.find("./models/model[@name='HX_SNOWMAN_DRUMMER']")

    assert drummer is not None
    assert len([model for model in models if model.attrib.get("name") == "HX_SNOWMAN_DRUMMER"]) == 1
    assert drummer.attrib["DisplayAs"] == "Custom"
    assert drummer.attrib["HelixImplementationState"] == "drummer_v3_beta"
    assert drummer.attrib["HelixSourceModel"] == "HX_SNOWMAN_DRUMMER_V3"
    assert drummer.attrib["StartChannel"] == "12345"
    assert drummer.attrib["WorldPosX"] == "1"
    assert drummer.attrib["CustomModel"]
    assert int(drummer.attrib["HelixNodeCount"]) > 1000
    assert result["submodel_count"] >= 35

    names = {submodel.attrib["name"] for submodel in drummer.findall("./subModel")}
    assert "HX_SNOWMAN_DRUMMER_HIT_SNARE" in names
    assert "HX_SNOWMAN_DRUMMER_HIT_BOTH_CRASH" in names
    assert all(not name.startswith("HX_SNOWMAN_DRUMMER_V3_") for name in names)
