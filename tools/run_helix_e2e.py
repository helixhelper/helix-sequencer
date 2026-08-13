from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "template.xsq"
DEFAULT_LAYOUT = ROOT / "xlights_rgbeffects.xml"


def _duration(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    try:
        import imageio.v2 as imageio

        reader = imageio.get_reader(str(path), "ffmpeg")
        meta = reader.get_meta_data()
        reader.close()
        return float(meta.get("duration") or 0.0)
    except Exception:
        return 0.0


def _run(command: list[str]) -> None:
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def _inspect_xsq(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    timing = [e for e in root.findall(".//Element") if e.attrib.get("type") == "timing"]
    model_elements = [e for e in root.findall(".//Element") if e.attrib.get("type") == "model"]
    effects = root.findall(".//Effect")
    return {
        "valid_xml": True,
        "media_file": root.findtext("head/mediaFile"),
        "sequence_duration": float(root.findtext("head/sequenceDuration") or 0.0),
        "timing_tracks": len(timing),
        "model_elements": len(model_elements),
        "effects": len(effects),
    }


def _inspect_drummer(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "event_count": 0, "eight_channel_ready": False}
    payload = json.loads(path.read_text(encoding="utf-8"))
    kit = payload.get("kit") if isinstance(payload, dict) else {}
    drum_intelligence = (kit or {}).get("drum_intelligence") or {}
    cues = ((payload.get("cues") or {}).get("drummer") or []) if isinstance(payload, dict) else []
    motion_events = drum_intelligence.get("motion_events") or []
    cue_submodels = {str(cue.get("submodel")) for cue in cues if cue.get("submodel")}
    motion_submodels = {str(submodel) for event in motion_events for submodel in (event.get("submodels") or [])}
    event_kinds = {str(cue.get("kind")) for cue in cues if cue.get("kind")}
    physical_channels = {
        "kick": "kick" in cue_submodels or "kick" in event_kinds,
        "snare": "snare" in cue_submodels or "snare" in event_kinds,
        "hi_hat": "hi_hat" in cue_submodels or "hihat" in event_kinds,
        "tom": "tom" in cue_submodels or "tom" in event_kinds,
        "cymbal": "cymbal" in cue_submodels or "cymbal" in event_kinds,
        "left_stick": "left_stick" in motion_submodels,
        "right_stick": "right_stick" in motion_submodels,
        "drum_bus": "drum_bus" in cue_submodels or "drum_bus" in event_kinds,
    }
    return {
        "available": True,
        "event_count": len(cues),
        "mode": drum_intelligence.get("fallback_mode"),
        "counts": drum_intelligence.get("counts", {}),
        "physical_channels": physical_channels,
        "eight_channel_ready": all(physical_channels.values()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Helix audio-to-XSQ-to-MP4 end-to-end.")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--profile", default="master")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audio = args.audio.resolve()
    run_dir = (args.output_dir / audio.stem).resolve()
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    media_dir = run_dir / "media"
    media_dir.mkdir()
    copied_audio = media_dir / audio.name
    shutil.copy2(audio, copied_audio)
    manifest: dict[str, Any] = {
        "status": "failed",
        "input_audio": str(copied_audio),
        "duration": _duration(copied_audio),
        "profile": args.profile,
        "orchestration": False,
        "audio_analysis": False,
        "beat_grid": False,
        "drummer": False,
        "mapping": False,
        "xsq_generated": False,
        "xsq_validated": False,
        "mp4_rendered": False,
        "artifacts": {},
    }
    manifest_path = run_dir / "run_manifest.json"
    try:
        _run([
            sys.executable, "main.py", "--profile", args.profile, "--", str(copied_audio),
            "--template", str(args.template.resolve()), "--layout-file", str(args.layout.resolve()),
            "--single", "--output-dir", str(run_dir), "--variants", "1", "--no-prompt",
            "--no-save-settings", "--no-workspace-history", "--no-polish", "--audio-reactive-profile", "balanced",
        ])
        xsq_matches = sorted(run_dir.glob(f"{copied_audio.stem},*.xsq"))
        if not xsq_matches:
            raise FileNotFoundError(f"No generated XSQ found in {run_dir}")
        xsq = xsq_matches[0]
        stem = xsq.stem
        report = run_dir / f"{stem}.report.json"
        orchestration = run_dir / f"{copied_audio.stem}.effects_orchestration.json"
        snowman = run_dir / f"{stem}.snowman_band.json"
        inspection = _inspect_xsq(xsq)
        drummer_inspection = _inspect_drummer(snowman)
        validation = {"status": "success", **inspection, "drummer": drummer_inspection}
        (run_dir / "validation_report.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
        _run([
            sys.executable, "-m", "tools.preview_renderer", str(xsq), "--layout", str(args.layout.resolve()),
            "--audio", str(copied_audio), "--fps", str(args.fps), "--width", str(args.width), "--height", str(args.height),
        ])
        mp4 = xsq.with_suffix(".mp4")
        manifest.update({
            "status": "success",
            "duration": inspection["sequence_duration"] or manifest.get("duration", 0.0),
            "orchestration": orchestration.exists(),
            "audio_analysis": report.exists(),
            "beat_grid": inspection["timing_tracks"] > 0,
            "drummer": bool(drummer_inspection["eight_channel_ready"]),
            "mapping": inspection["effects"] > 0 and inspection["model_elements"] >= 256,
            "xsq_generated": xsq.exists(),
            "xsq_validated": validation["status"] == "success",
            "mp4_rendered": mp4.exists(),
            "artifacts": {"xsq": str(xsq), "mp4": str(mp4), "validation_report": str(run_dir / "validation_report.json")},
        })
        return 0
    except Exception as exc:
        manifest["failure_stage"] = type(exc).__name__
        manifest["error"] = str(exc)
        return 1
    finally:
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    raise SystemExit(main())
