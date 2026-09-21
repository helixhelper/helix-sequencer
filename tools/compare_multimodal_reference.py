from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.lms_calibration import load_lms_calibration
from core.multimodal_reference import compare_candidate_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare a Helix preview with a section-level physical-show reference."
    )
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--candidate-video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sample-fps", type=float, default=4.0)
    args = parser.parse_args(argv)
    profile = load_lms_calibration(args.calibration)
    comparison = compare_candidate_video(
        candidate_video_path=args.candidate_video,
        profile=profile,
        sample_fps=args.sample_fps,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print({"output": str(output), "score": comparison["overall_score"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
