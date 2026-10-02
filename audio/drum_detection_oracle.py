from __future__ import annotations

"""Approved placeholder-era drummer behavior oracle.

This module intentionally preserves the single-label, onset-driven drum detector
used by the drummer preview that was accepted as the behavioral ground truth.
Newer multi-family / flux-recall analysis remains available in
:mod:`audio.drum_detection`, but production drummer injection can opt into
this oracle so visual upgrades do not silently change the performance.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import librosa
import numpy as np

from audio.drum_classification import DrumEvent, empty_drum_streams, stream_key_for_type


APPROVED_DRUMMER_BEHAVIOR_PROFILE = "placeholder_v1_b27e8d7"


@dataclass(frozen=True)
class OracleDrumDetectionConfig:
    onset_delta: float = 0.045
    onset_wait: int = 1
    min_gap_ms: int = 22
    low_confidence_min: float = 0.34
    cluster_gap_ms: int = 95
    prefer_recall: bool = True


@dataclass(frozen=True)
class OracleDrumClassifierThresholds:
    low_confidence_min: float = 0.34
    kick_low_ratio_min: float = 0.24
    kick_low_centroid_max: float = 700.0
    snare_mid_ratio_min: float = 0.20
    snare_sharpness_min: float = 0.08
    tom_mid_low_ratio_min: float = 0.22
    hihat_high_ratio_min: float = 0.38
    hihat_decay_max: float = 0.42
    cymbal_high_ratio_min: float = 0.32
    cymbal_decay_min: float = 0.42


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def classify_drum_hit_oracle(
    features: dict[str, float],
    thresholds: OracleDrumClassifierThresholds = OracleDrumClassifierThresholds(),
) -> tuple[str, float]:
    """Classify exactly one family using the approved placeholder-era rules."""
    low = _clamp(features.get("low_ratio", 0.0))
    mid_low = _clamp(features.get("mid_low_ratio", 0.0))
    mid = _clamp(features.get("mid_ratio", 0.0))
    high = _clamp(features.get("high_ratio", 0.0))
    centroid = float(features.get("centroid_hz", 0.0) or 0.0)
    low_centroid = float(features.get("low_centroid_hz", centroid) or centroid)
    spread = _clamp(features.get("spectral_spread01", 0.0))
    sharp = _clamp(features.get("transient_sharpness", 0.0))
    decay = _clamp(features.get("decay_profile", 0.0))

    if low >= thresholds.kick_low_ratio_min and low_centroid <= thresholds.kick_low_centroid_max:
        confidence = _clamp(
            (low * 0.55)
            + (0.25 * (1.0 - min(1.0, low_centroid / 700.0)))
            + (sharp * 0.20)
        )
        return "kick", round(confidence, 3)

    if (
        high >= thresholds.hihat_high_ratio_min
        and decay <= thresholds.hihat_decay_max
        and sharp >= thresholds.snare_sharpness_min
    ):
        confidence = _clamp((high * 0.55) + (sharp * 0.30) + ((1.0 - decay) * 0.15))
        return "hihat", round(confidence, 3)

    if high >= thresholds.cymbal_high_ratio_min and decay >= thresholds.cymbal_decay_min:
        confidence = _clamp((high * 0.45) + (decay * 0.35) + (spread * 0.20))
        return "cymbal", round(confidence, 3)

    if (
        mid >= thresholds.snare_mid_ratio_min
        and sharp >= thresholds.snare_sharpness_min
        and high < 0.60
        and mid_low < 0.35
    ):
        confidence = _clamp(
            (mid * 0.48)
            + (sharp * 0.30)
            + (spread * 0.12)
            + ((1.0 - high) * 0.10)
        )
        return "snare", round(confidence, 3)

    if mid_low >= thresholds.tom_mid_low_ratio_min and high < 0.50 and centroid < 2200:
        confidence = _clamp(
            (mid_low * 0.52)
            + (1.0 - min(1.0, abs(centroid - 900.0) / 1800.0)) * 0.20
            + (decay * 0.18)
            + (sharp * 0.10)
        )
        return "tom", round(confidence, 3)

    candidates: list[tuple[str, float]] = [
        ("kick", (low * 0.55) + ((1.0 - min(1.0, low_centroid / 1200.0)) * 0.25) + (sharp * 0.20)),
        ("snare", (mid * 0.42) + (sharp * 0.32) + (spread * 0.18) + (mid_low * 0.08)),
        ("tom", (mid_low * 0.48) + ((1.0 - abs(centroid - 900.0) / 1800.0) * 0.22) + (decay * 0.16) + (sharp * 0.14)),
        ("hihat", (high * 0.56) + (sharp * 0.28) + ((1.0 - decay) * 0.16)),
        ("cymbal", (high * 0.42) + (decay * 0.36) + (spread * 0.22)),
    ]
    drum_type, score = max(candidates, key=lambda item: item[1])

    if drum_type == "kick" and low < thresholds.kick_low_ratio_min:
        score *= 0.78
    if drum_type == "snare" and mid < thresholds.snare_mid_ratio_min:
        score *= 0.78
    if drum_type == "tom" and mid_low < thresholds.tom_mid_low_ratio_min:
        score *= 0.76
    if drum_type == "hihat" and high < thresholds.hihat_high_ratio_min:
        score *= 0.72
    if drum_type == "cymbal" and (
        high < thresholds.cymbal_high_ratio_min or decay < thresholds.cymbal_decay_min
    ):
        score *= 0.78

    confidence = _clamp(score)
    if confidence < thresholds.low_confidence_min:
        return "drum_bus", round(confidence, 3)
    return drum_type, round(confidence, 3)


def _norm01(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return arr
    top = float(np.max(np.abs(arr)))
    return arr / top if top > 1e-9 else np.zeros_like(arr)


def _band_energy(freqs: np.ndarray, spectrum: np.ndarray, low: float, high: float) -> float:
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask):
        return 0.0
    return float(np.sum(spectrum[mask]))


def _band_centroid(freqs: np.ndarray, spectrum: np.ndarray, low: float, high: float) -> float:
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask):
        return 0.0
    band = spectrum[mask]
    total = float(np.sum(band))
    if total <= 1e-9:
        return 0.0
    return float(np.sum(freqs[mask] * band) / total)


def _compress_events(events: list[DrumEvent], min_gap_ms: int) -> list[DrumEvent]:
    out: list[DrumEvent] = []
    for event in sorted(events, key=lambda item: (item.timestamp, item.drum_type)):
        if (
            out
            and event.timestamp_ms - out[-1].timestamp_ms < min_gap_ms
            and event.drum_type == out[-1].drum_type
        ):
            if event.velocity > out[-1].velocity:
                out[-1] = event
            continue
        out.append(event)
    return out


def _cluster_id(
    timestamp_ms: int,
    previous_ms: int | None,
    current_cluster: int,
    gap_ms: int,
) -> tuple[int, int]:
    if previous_ms is None or timestamp_ms - previous_ms > gap_ms:
        current_cluster += 1
    return current_cluster, current_cluster


def detect_drum_event_streams_oracle(
    y: np.ndarray,
    sr: int,
    config: OracleDrumDetectionConfig = OracleDrumDetectionConfig(),
    *,
    source_label: str = "approved_placeholder_oracle",
) -> dict[str, list[DrumEvent]]:
    """Return the approved onset-only, one-family-per-onset event streams."""
    y = np.asarray(y, dtype=np.float32).reshape(-1)
    if y.size == 0 or sr <= 0:
        return empty_drum_streams()

    _, perc = librosa.effects.hpss(y)
    hop = 512
    n_fft = 2048
    onset_env = librosa.onset.onset_strength(y=perc, sr=sr, hop_length=hop)
    if onset_env.size == 0:
        return empty_drum_streams()

    frames = librosa.onset.onset_detect(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=hop,
        backtrack=False,
        delta=config.onset_delta,
        wait=max(1, config.onset_wait),
    )
    if frames.size == 0 and config.prefer_recall:
        frames = np.asarray(
            librosa.util.peak_pick(
                _norm01(onset_env),
                pre_max=1,
                post_max=1,
                pre_avg=2,
                post_avg=2,
                delta=0.025,
                wait=1,
            ),
            dtype=int,
        )

    stft = np.abs(librosa.stft(perc, n_fft=n_fft, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    rms = librosa.feature.rms(y=perc, hop_length=hop)[0]
    rms01 = _norm01(rms)
    onset01 = _norm01(onset_env)

    raw_events: list[DrumEvent] = []
    previous_ms: int | None = None
    cluster = -1
    for frame in sorted(set(int(frame) for frame in frames if int(frame) < stft.shape[1])):
        spectrum = stft[:, frame]
        total = float(np.sum(spectrum)) + 1e-9
        low = _band_energy(freqs, spectrum, 20, 250)
        mid_low = _band_energy(freqs, spectrum, 160, 700)
        mid = _band_energy(freqs, spectrum, 700, 2500)
        high = _band_energy(freqs, spectrum, 2500, min(sr / 2, 14000))
        centroid = float(
            librosa.feature.spectral_centroid(
                S=spectrum.reshape(-1, 1), sr=sr
            )[0, 0]
        )
        spread = float(
            librosa.feature.spectral_bandwidth(
                S=spectrum.reshape(-1, 1), sr=sr
            )[0, 0]
        )
        low_centroid = _band_centroid(freqs, spectrum, 20, 700)

        attack_slice = rms01[frame : min(len(rms01), frame + 2)]
        tail_slice = rms01[
            min(len(rms01), frame + 4) : min(len(rms01), frame + 10)
        ]
        attack_level = float(np.mean(attack_slice)) if attack_slice.size else 0.0
        tail_level = float(np.mean(tail_slice)) if tail_slice.size else 0.0
        decay = tail_level / max(attack_level, 1e-6)

        previous = (
            float(onset01[frame - 1])
            if frame > 0 and frame - 1 < len(onset01)
            else 0.0
        )
        current = float(onset01[frame]) if frame < len(onset01) else 0.0
        sharp = max(0.0, current - previous)
        features = {
            "low_ratio": low / total,
            "mid_low_ratio": mid_low / total,
            "mid_ratio": mid / total,
            "high_ratio": high / total,
            "centroid_hz": centroid,
            "low_centroid_hz": low_centroid,
            "spectral_spread01": min(1.0, spread / max(1.0, sr / 2)),
            "transient_sharpness": min(1.0, sharp),
            "decay_profile": min(1.0, decay),
        }
        drum_type, confidence = classify_drum_hit_oracle(
            features,
            OracleDrumClassifierThresholds(
                low_confidence_min=config.low_confidence_min
            ),
        )
        timestamp = float(
            librosa.frames_to_time(frame, sr=sr, hop_length=hop)
        )
        timestamp_ms = int(round(timestamp * 1000.0))
        cluster, cluster_id = _cluster_id(
            timestamp_ms, previous_ms, cluster, config.cluster_gap_ms
        )
        previous_ms = timestamp_ms
        velocity = max(
            0.08,
            min(
                1.0,
                (
                    float(rms01[frame])
                    if frame < len(rms01)
                    else current
                )
                * 0.65
                + current * 0.35,
            ),
        )
        raw_events.append(
            DrumEvent(
                timestamp=round(timestamp, 4),
                velocity=round(velocity, 3),
                confidence=confidence,
                frequency_band_info={
                    key: round(float(value), 4)
                    for key, value in features.items()
                },
                cluster_id=cluster_id,
                drum_type=drum_type,
                source=source_label,
            )
        )

    streams = empty_drum_streams()
    for event in _compress_events(raw_events, config.min_gap_ms):
        streams[stream_key_for_type(event.drum_type)].append(event)
    return streams


def detect_drum_event_streams_from_file_oracle(
    path: Path,
    config: OracleDrumDetectionConfig = OracleDrumDetectionConfig(),
    log_fn: Callable[[str], None] | None = None,
    *,
    source_label: str = "approved_placeholder_oracle",
) -> dict[str, list[DrumEvent]]:
    try:
        y, sr = librosa.load(str(path), sr=None, mono=True)
        streams = detect_drum_event_streams_oracle(
            np.asarray(y, dtype=np.float32),
            int(sr),
            config,
            source_label=source_label,
        )
        if log_fn is not None:
            counts = {key: len(value) for key, value in streams.items()}
            log_fn(
                f"Drummer behavior oracle ({APPROVED_DRUMMER_BEHAVIOR_PROFILE}): {counts}"
            )
        return streams
    except Exception as exc:
        if log_fn is not None:
            log_fn(f"Drummer behavior oracle skipped: {exc}")
        return empty_drum_streams()
