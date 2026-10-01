from __future__ import annotations

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_IMAGE = ROOT / "fixtures" / "band_geometry" / "source" / "drummerbg.png"

LAYER_BY_TARGET = {
    "HX_SNOWMAN_DRUMMER_HIT_KICK": ROOT / "fixtures" / "band_geometry" / "layers" / "drummer_hit_kick.png",
    "HX_SNOWMAN_DRUMMER_HIT_SNARE": ROOT / "fixtures" / "band_geometry" / "layers" / "drummer_hit_snare.png",
    "HX_SNOWMAN_DRUMMER_HIT_HI_HAT": ROOT / "fixtures" / "band_geometry" / "layers" / "drummer_hit_hi_hat.png",
    "HX_SNOWMAN_DRUMMER_HIT_TOM_LEFT": ROOT / "fixtures" / "band_geometry" / "layers" / "drummer_hit_left_tom.png",
    "HX_SNOWMAN_DRUMMER_HIT_TOM_RIGHT": ROOT / "fixtures" / "band_geometry" / "layers" / "drummer_hit_right_tom.png",
    "HX_SNOWMAN_DRUMMER_HIT_TOM_FLOOR": ROOT / "fixtures" / "band_geometry" / "layers" / "drummer_hit_floor_tom.png",
    "HX_SNOWMAN_DRUMMER_HIT_CYMBAL_LEFT": ROOT / "fixtures" / "band_geometry" / "layers" / "drummer_hit_left_crash.png",
    "HX_SNOWMAN_DRUMMER_HIT_CYMBAL_RIGHT": ROOT / "fixtures" / "band_geometry" / "layers" / "drummer_hit_right_crash.png",
}


def _effect_intensity(settings: str) -> float:
    match = re.search(r"E_SLIDER_Brightness=([0-9.]+)", settings or "")
    if not match:
        return 1.0
    try:
        return max(0.08, min(1.0, float(match.group(1))))
    except ValueError:
        return 1.0


def parse_effects(xsq: Path) -> list[tuple[int, int, str, float]]:
    root = ET.parse(xsq).getroot()
    out: list[tuple[int, int, str, float]] = []
    for element in root.findall("./ElementEffects/Element"):
        name = element.get("name", "")
        if name not in LAYER_BY_TARGET:
            continue
        for layer in element.findall("EffectLayer"):
            for fx in layer.findall("Effect"):
                out.append(
                    (
                        int(float(fx.get("startTime", "0"))),
                        int(float(fx.get("endTime", "0"))),
                        name,
                        _effect_intensity(fx.get("settings", "")),
                    )
                )
    return sorted(out)


def _fit_on_canvas(image: Image.Image, width: int, height: int) -> Image.Image:
    source = image.convert("RGBA")
    scale = min(width / source.width, height / source.height)
    size = (
        max(1, round(source.width * scale)),
        max(1, round(source.height * scale)),
    )
    resized = source.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (7, 10, 18, 255))
    x = (width - size[0]) // 2
    y = (height - size[1]) // 2
    canvas.alpha_composite(resized, (x, y))
    return canvas


def prepare_visual_assets(
    width: int = 960,
    height: int = 540,
) -> tuple[Image.Image, dict[str, Image.Image]]:
    if not SOURCE_IMAGE.exists():
        raise FileNotFoundError(f"Missing approved drummer source image: {SOURCE_IMAGE}")

    with Image.open(SOURCE_IMAGE) as source:
        source_rgba = source.convert("RGBA")
        source_size = source_rgba.size
        base = _fit_on_canvas(source_rgba, width, height)

    overlays: dict[str, Image.Image] = {}
    for target, path in LAYER_BY_TARGET.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing approved drummer hit layer for {target}: {path}")
        with Image.open(path) as layer:
            rgba = layer.convert("RGBA")
            if rgba.size != source_size:
                raise ValueError(
                    f"Drummer layer size mismatch for {target}: {rgba.size} != {source_size}"
                )
            transparent = Image.new("RGBA", source_size, (0, 0, 0, 0))
            transparent.alpha_composite(rgba)
            scale = min(width / source_size[0], height / source_size[1])
            size = (
                max(1, round(source_size[0] * scale)),
                max(1, round(source_size[1] * scale)),
            )
            resized = transparent.resize(size, Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            canvas.alpha_composite(
                resized,
                ((width - size[0]) // 2, (height - size[1]) // 2),
            )
            overlays[target] = canvas
    return base, overlays


def _scaled_alpha(layer: Image.Image, intensity: float) -> Image.Image:
    amount = max(0.0, min(1.0, float(intensity)))
    if amount >= 0.999:
        return layer
    scaled = layer.copy()
    alpha = scaled.getchannel("A")
    alpha = alpha.point(lambda value: int(round(value * amount)))
    scaled.putalpha(alpha)
    return scaled


def compose_drummer_frame(
    base: Image.Image,
    overlays: dict[str, Image.Image],
    active: dict[str, float],
) -> Image.Image:
    """Composite approved hit layers over the immutable approved drummer art."""
    frame = base.copy()
    for target, intensity in active.items():
        if intensity <= 0.02:
            continue
        overlay = overlays.get(target)
        if overlay is None:
            continue
        frame.alpha_composite(_scaled_alpha(overlay, intensity))
    return frame.convert("RGB")


def _audio_duration_ms(audio: Path) -> int:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [ff, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(audio)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
            duration = float(data["format"]["duration"])
            if duration > 0:
                return int(round(duration * 1000.0))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass

    probe = subprocess.run([ff, "-i", str(audio)], capture_output=True, text=True)
    marker = "Duration: "
    for line in probe.stderr.splitlines():
        if marker in line:
            value = line.split(marker, 1)[1].split(",", 1)[0].strip()
            h, m, s = value.split(":")
            return int(
                round(
                    (int(h) * 3600 + int(m) * 60 + float(s)) * 1000.0
                )
            )
    raise RuntimeError(f"Unable to determine audio duration for {audio}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xsq", type=Path)
    ap.add_argument("--audio", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Optional debug cap in seconds; default renders the entire audio.",
    )
    args = ap.parse_args()

    effects = parse_effects(args.xsq)
    if not effects:
        raise SystemExit("FAIL: no real HX_SNOWMAN_DRUMMER hit-composite effects found")

    audio_duration_ms = _audio_duration_ms(args.audio)
    effect_end_ms = max(effect[1] for effect in effects)
    if effect_end_ms < int(audio_duration_ms * 0.95):
        raise SystemExit(
            f"FAIL: drummer XSQ ends at {effect_end_ms} ms, but repo audio is "
            f"{audio_duration_ms} ms; refusing to render a partial performance"
        )

    duration_ms = (
        audio_duration_ms
        if args.duration <= 0
        else min(int(args.duration * 1000), audio_duration_ms)
    )
    base, overlays = prepare_visual_assets(960, 540)

    out = args.output
    silent = out.with_suffix(".silent.mp4")
    writer = imageio.get_writer(
        silent,
        fps=args.fps,
        codec="libx264",
        quality=8,
        macro_block_size=None,
    )

    try:
        frame_count = int(duration_ms / 1000 * args.fps)
        for index in range(frame_count):
            t_ms = int(index * 1000 / args.fps)
            active = {name: 0.0 for name in LAYER_BY_TARGET}
            for start, end, name, intensity in effects:
                if start <= t_ms < end:
                    active[name] = max(active[name], intensity)
            writer.append_data(
                np.asarray(compose_drummer_frame(base, overlays, active))
            )
    finally:
        writer.close()

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ff,
        "-y",
        "-i",
        str(silent),
        "-i",
        str(args.audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr[-4000:])
    silent.unlink(missing_ok=True)

    if not out.exists() or out.stat().st_size < 10000:
        raise SystemExit("FAIL: drummer MP4 missing/empty")

    print(
        "PASS: approved drummer visual ground truth rendered "
        f"targets={len(LAYER_BY_TARGET)} effects={len(effects)} "
        f"duration_ms={duration_ms} audio_duration_ms={audio_duration_ms}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
