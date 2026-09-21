from __future__ import annotations

import argparse

from core.multimodal_reference import build_multimodal_reference, write_multimodal_reference


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an aggregate section-level Helix calibration from LMS and real-life video."
    )
    parser.add_argument("--lms", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--sections", required=True)
    parser.add_argument("--audio")
    parser.add_argument("--video-offset-seconds", type=float, default=0.0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--acknowledge-reference-rights", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_multimodal_reference(
        lms_path=args.lms,
        video_path=args.video,
        section_spec_path=args.sections,
        audio_path=args.audio,
        video_offset_seconds=args.video_offset_seconds,
        acknowledge_reference_rights=args.acknowledge_reference_rights,
    )
    output = write_multimodal_reference(args.output, payload)
    print({"output": str(output), "sections": payload["provenance"]["section_count"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
