from __future__ import annotations

import argparse
from pathlib import Path

from core.lms_calibration import LmsInspectionReport, inspect_lms


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect a local Light-O-Rama LMS file for aggregate Helix calibration."
    )
    parser.add_argument("lms_file")
    parser.add_argument("--output", help="Optional JSON output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = inspect_lms(Path(args.lms_file))
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.to_json() + "\n", encoding="utf-8")
        print({"output": str(output)})
    else:
        print(report.to_json())
    fatal_prefixes = ("Missing", "Could not parse")
    return 0 if not any(item.startswith(fatal_prefixes) for item in report.warnings) else 1


__all__ = ["LmsInspectionReport", "inspect_lms", "build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
