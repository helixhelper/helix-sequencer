from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from core.xlights_layout_compat import normalize_xlights_model_types, preflight_xlights_layout


def inspect_layout(layout_path: Path, *, fix: bool = False, backup: bool = True) -> dict[str, Any]:
    """Inspect an xLights layout and optionally repair safe compatibility aliases.

    The doctor only applies deterministic compatibility rewrites already used by
    the beta finalizer. It does not invent missing models, groups, or channel
    assignments. Structural problems remain reported as blocking errors.
    """

    layout = Path(layout_path)
    result: dict[str, Any] = {
        "layout": str(layout.resolve(strict=False)),
        "fix_requested": bool(fix),
        "backup_path": "",
        "normalization": {},
    }

    if fix and layout.exists():
        if backup:
            backup_path = layout.with_suffix(layout.suffix + ".pre-helix-doctor.bak")
            shutil.copy2(layout, backup_path)
            result["backup_path"] = str(backup_path)
        result["normalization"] = normalize_xlights_model_types(layout)

    report = preflight_xlights_layout(layout)
    result.update(report)
    result["ready_for_helix"] = bool(report.get("ok"))
    return result


def _human_summary(result: dict[str, Any]) -> str:
    lines = ["XLIGHTS LAYOUT DOCTOR"]
    lines.append(f"Layout: {result.get('layout', '')}")
    lines.append(f"Models: {int(result.get('models', 0) or 0)}")
    lines.append(f"Groups: {int(result.get('groups', 0) or 0)}")

    normalization = dict(result.get("normalization", {}) or {})
    changed = int(normalization.get("changed", 0) or 0)
    if changed:
        lines.append(f"Compatibility repairs: {changed}")
        horizontal = int(normalization.get("matrix_horizontal", 0) or 0)
        vertical = int(normalization.get("matrix_vertical", 0) or 0)
        lines.append(f"Matrix orientations: {horizontal} horizontal / {vertical} vertical")
        ambiguous = list(normalization.get("ambiguous_matrices", []) or [])
        if ambiguous:
            lines.append("Ambiguous matrices (horizontal fallback): " + ", ".join(str(item) for item in ambiguous))

    warnings = [str(item) for item in list(result.get("warnings", []) or [])]
    errors = [str(item) for item in list(result.get("errors", []) or [])]
    for warning in warnings:
        lines.append(f"WARN: {warning}")
    for error in errors:
        lines.append(f"BLOCKED: {error}")

    lines.append("READY TO GENERATE" if result.get("ready_for_helix") else "NOT READY")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preflight an xLights layout before Helix generation and optionally repair safe compatibility aliases."
    )
    parser.add_argument("layout", help="Path to xlights_rgbeffects.xml or compatible layout XML.")
    parser.add_argument("--fix", action="store_true", help="Apply safe xLights compatibility rewrites before validation.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a .pre-helix-doctor.bak copy when --fix is used.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of a human summary.")
    parser.add_argument("--out", help="Optional path to save the JSON report.")
    args = parser.parse_args(argv)

    result = inspect_layout(Path(args.layout), fix=bool(args.fix), backup=not bool(args.no_backup))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_human_summary(result))
    return 0 if result.get("ready_for_helix") else 2


if __name__ == "__main__":
    raise SystemExit(main())
