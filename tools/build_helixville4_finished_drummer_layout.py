from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from tools.build_helpers.helixia import build_helixia_layout
from tools.build_helpers.helixville4_finished_band import add_finished_helixville4_band_models
from tools.build_helpers.drummer_v3_layout import install_drummer_v3_layout_model
from tools.write_helixville4_band_assets import write_band_assets


def build_finished_drummer_layout(output_dir: str | Path) -> dict[str, object]:
    out_dir = Path(output_dir)
    payload = build_helixia_layout(out_dir, use_helixville4_band_model_specs=False)
    layout_path = out_dir / "xlights_rgbeffects.xml"
    add_finished_helixville4_band_models(layout_path)
    drummer_v3 = install_drummer_v3_layout_model(layout_path)
    band_assets = write_band_assets(out_dir / "band_assets")
    payload["finished_band_export"] = {
        "schema": "helixville4.finished_band_export.v1",
        "drummer_model": "HX_SNOWMAN_DRUMMER",
        "drummer_state": "drummer_v3_beta",
        "drummer_submodel_count": drummer_v3["submodel_count"],
        "drummer_node_count": drummer_v3["node_count"],
        "drummer_pose_submodels": drummer_v3["pose_submodels"],
        "drummer_visual_target": "fixtures/band_geometry/previews/HX_SNOWMAN_DRUMMER_V3_pose_sheet.png",
        "layout_path": str(layout_path),
        "remaining_members_state": "approved_v2_runtime_models",
    }
    payload["band_assets"] = band_assets
    payload["xlights_layout"] = dict(payload.get("xlights_layout", {}))
    payload["xlights_layout"]["band_model_specs_enabled"] = True
    payload["xlights_layout"]["finished_drummer_enabled"] = True
    payload["xlights_layout"]["drummer_v3_enabled"] = True
    (out_dir / "helixia_manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out_dir / "HELIXIA_LAYOUT_NOTES.txt").write_text(
        "Helixville4 beta band layout generated.\n"
        "HX_SNOWMAN_DRUMMER uses authored Drummer V3 geometry and pose composite submodels.\n"
        "Singer, guitarist, and bassist use the approved V2 runtime models.\n",
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Helixville4 with the authored Drummer V3 model wired into xLights XML.")
    parser.add_argument("--output-dir", type=Path, default=Path("test_runs/helixville4_finished_drummer"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_finished_drummer_layout(args.output_dir)
    print(json.dumps(payload.get("finished_band_export", {}), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
