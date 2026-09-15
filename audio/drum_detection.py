from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import librosa
import numpy as np

from audio.drum_classification import DrumClassifierThresholds, DrumEvent, classify_drum_hit, empty_drum_streams, stream_key_for_type


DRUM_MIN_GAP_MS = {
    "kick": 70,
    "snare": 70,
    "tom": 85,
    "hihat": 24,
    "cymbal": 130,
    "drum_bus": 22,
}


@dataclass(frozen=True)
class DrumDetectionConfig:
    onset_delta: float = 0.045
    onset_wait: int = 1
    min_gap_ms: int = 22
    low_confidence_min: float = 0.34
    cluster_gap_ms: int = 95
    prefer_recall: bool = True
    fft_size: int = 2048
    hop_length: int = 256
    decay_early_ms: int = 35
    decay_late_ms: int = 150


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


def _band_energy_curve(
    freqs: np.ndarray,
    spectrogram: np.ndarray,
    low: float,
    high: float,
) -> np.ndarray:
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask) or spectrogram.ndim != 2:
        return np.zeros(spectrogram.shape[1] if spectrogram.ndim == 2 else 0, dtype=float)
    return _norm01(np.sum(spectrogram[mask, :], axis=0))


def _band_mean_curve(
    freqs: np.ndarray,
    spectrogram: np.ndarray,
    low: float,
    high: float,
) -> np.ndarray:
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask) or spectrogram.ndim != 2:
        return np.zeros(spectrogram.shape[1] if spectrogram.ndim == 2 else 0, dtype=float)
    return np.mean(spectrogram[mask, :], axis=0)


def _spectral_flux_peaks(
    energy: np.ndarray,
    *,
    hop_seconds: float,
    min_ioi_seconds: float,
    threshold_std: float,
) -> list[tuple[int, float]]:
    values = np.asarray(energy, dtype=float).reshape(-1)
    if values.size < 5:
        return []
    flux = np.maximum(0.0, np.diff(values, prepend=values[0]))
    flux = np.convolve(flux, np.asarray((0.25, 0.5, 0.25)), mode="same")
    top = float(np.max(flux))
    if top <= 1e-9:
        return []
    normalized = flux / top
    window = max(12, int(round(0.9 / max(1e-6, hop_seconds))))
    kernel = np.ones(window, dtype=float) / float(window)
    mean = np.convolve(normalized, kernel, mode="same")
    mean_square = np.convolve(normalized * normalized, kernel, mode="same")
    std = np.sqrt(np.maximum(0.0, mean_square - (mean * mean)))
    min_frames = max(1, int(round(min_ioi_seconds / max(1e-6, hop_seconds))))
    peaks: list[tuple[int, float]] = []
    for frame in range(2, len(normalized) - 2):
        value = float(normalized[frame])
        if value < normalized[frame - 1] or value < normalized[frame + 1]:
            continue
        if value < normalized[frame - 2] * 0.92:
            continue
        if value < float(mean[frame] + threshold_std * std[frame] + 0.01):
            continue
        if peaks and frame - peaks[-1][0] < min_frames:
            if value > peaks[-1][1]:
                peaks[-1] = (frame, value)
            continue
        peaks.append((frame, value))
    return peaks


def _multiband_peak_candidates(
    spectrogram: np.ndarray,
    freqs: np.ndarray,
    *,
    sr: int,
    hop_length: int,
) -> dict[str, list[tuple[int, float]]]:
    nyquist = max(100.0, (sr / 2.0) - 80.0)
    low = _band_mean_curve(freqs, spectrogram, 30, 250)
    kick = _band_mean_curve(freqs, spectrogram, 30, 95)
    click = _band_mean_curve(freqs, spectrogram, 1600, min(3800, nyquist))
    snare_body = _band_mean_curve(freqs, spectrogram, 150, 380)
    snare_crack = _band_mean_curve(freqs, spectrogram, 2400, min(7200, nyquist))
    tom = _band_mean_curve(freqs, spectrogram, 90, 230)
    hat = _band_mean_curve(freqs, spectrogram, min(6200, nyquist * 0.6), nyquist)
    cymbal = _band_mean_curve(freqs, spectrogram, 2800, min(11000, nyquist))
    hop_seconds = hop_length / float(sr)
    lanes = {
        "kick": (kick + (0.28 * click), 0.08, 1.65),
        "snare": ((0.55 * snare_body) + snare_crack, 0.085, 1.85),
        "tom": ((0.85 * tom) + (0.15 * low), 0.10, 2.05),
        "hihat": (hat, 0.028, 1.12),
        "cymbal": (cymbal, 0.16, 1.85),
    }
    return {
        drum_type: _spectral_flux_peaks(
            energy,
            hop_seconds=hop_seconds,
            min_ioi_seconds=min_ioi,
            threshold_std=threshold,
        )
        for drum_type, (energy, min_ioi, threshold) in lanes.items()
    }


def _lane_confidence(
    drum_type: str,
    features: dict[str, float],
    peak_strength: float,
) -> float:
    low = float(features.get("low_ratio", 0.0))
    mid_low = float(features.get("mid_low_ratio", 0.0))
    mid = float(features.get("mid_ratio", 0.0))
    high = float(features.get("high_ratio", 0.0))
    centroid = float(features.get("centroid_hz", 0.0))
    sharp = float(features.get("transient_sharpness", 0.0))
    decay = float(features.get("decay_profile", 0.0))
    strength = max(0.0, min(1.0, float(peak_strength)))
    if drum_type == "kick":
        focus = float(features.get("kick_focus_ratio", 0.0))
        tom_focus = float(features.get("tom_focus_ratio", 0.0))
        if tom_focus > focus * 1.25 and mid_low > 0.20:
            return 0.0
        strong_lane = focus >= 0.04 and strength >= 0.45
        if focus < 0.075 and low < 0.18 and not strong_lane:
            return 0.0
        if centroid > 3500 and focus < 0.075 and not strong_lane:
            return 0.0
        return min(1.0, 0.28 + (0.32 * low) + (0.20 * focus) + (0.12 * sharp) + (0.08 * strength))
    if drum_type == "snare":
        body = float(features.get("snare_body_ratio", 0.0))
        crack = float(features.get("snare_crack_ratio", 0.0))
        if body < 0.045 or crack < 0.07 or low > 0.68 or centroid > 6800:
            return 0.0
        return min(1.0, 0.24 + (0.22 * (mid + mid_low)) + (0.18 * crack) + (0.16 * sharp) + (0.12 * strength))
    if drum_type == "tom":
        focus = float(features.get("tom_focus_ratio", 0.0))
        kick_focus = float(features.get("kick_focus_ratio", 0.0))
        if focus < 0.10 or high > 0.46 or centroid > 2100:
            return 0.0
        if centroid < 500 and kick_focus > focus:
            return 0.0
        return min(1.0, 0.27 + (0.28 * mid_low) + (0.22 * focus) + (0.11 * decay) + (0.12 * strength))
    if drum_type == "hihat":
        if high < 0.38 or centroid < 2000 or decay > 0.46:
            return 0.0
        return min(1.0, 0.30 + (0.30 * high) + (0.15 * (1.0 - decay)) + (0.13 * sharp) + (0.12 * strength))
    if drum_type == "cymbal":
        if high < 0.30 or decay < 0.32:
            return 0.0
        spread = float(features.get("spectral_spread01", 0.0))
        return min(1.0, 0.25 + (0.24 * high) + (0.23 * decay) + (0.14 * spread) + (0.14 * strength))
    return 0.0


def _decay_ratio(
    energy: np.ndarray,
    frame: int,
    *,
    sr: int,
    hop_length: int,
    early_ms: int = 35,
    late_ms: int = 150,
) -> float:
    """Measure sustained energy after a hit instead of absolute post-hit loudness.

    A short hat should approach zero by the late window, while a crash or ride
    keeps a larger fraction of its early energy.  Averaging normalized RMS made
    loud, short hits appear sustained and blurred that distinction.
    """

    values = np.asarray(energy, dtype=float).reshape(-1)
    if values.size == 0 or sr <= 0 or hop_length <= 0:
        return 0.0
    hop_ms = (1000.0 * hop_length) / float(sr)
    early_frames = max(2, int(round(max(1, early_ms) / hop_ms)))
    late_start = max(
        early_frames + 1,
        int(round(max(early_ms + 1, late_ms * 0.65) / hop_ms)),
    )
    late_end = max(
        late_start + 1,
        int(round(max(late_ms, early_ms + 1) / hop_ms)),
    )
    early = values[frame + 1 : min(values.size, frame + 1 + early_frames)]
    late = values[frame + late_start : min(values.size, frame + late_end + 1)]
    if early.size == 0:
        return 0.0
    early_level = float(np.max(early))
    if early_level <= 1e-9:
        return 0.0
    late_level = float(np.mean(late)) if late.size else 0.0
    return max(0.0, min(1.0, late_level / early_level))


def _compress_events(events: list[DrumEvent], min_gap_ms: int) -> list[DrumEvent]:
    out: list[DrumEvent] = []
    last_index_by_type: dict[str, int] = {}
    for event in sorted(events, key=lambda item: (item.timestamp, item.drum_type)):
        previous_index = last_index_by_type.get(event.drum_type)
        previous = out[previous_index] if previous_index is not None else None
        type_gap_ms = max(min_gap_ms, DRUM_MIN_GAP_MS.get(event.drum_type, min_gap_ms))
        if previous is not None and event.timestamp_ms - previous.timestamp_ms < type_gap_ms:
            event_score = (event.confidence * 0.65) + (event.velocity * 0.35)
            previous_score = (previous.confidence * 0.65) + (previous.velocity * 0.35)
            if event_score > previous_score:
                out[previous_index] = event
            continue
        last_index_by_type[event.drum_type] = len(out)
        out.append(event)
    return sorted(out, key=lambda item: (item.timestamp, item.drum_type))


def _cluster_id(timestamp_ms: int, previous_ms: int | None, current_cluster: int, gap_ms: int) -> tuple[int, int]:
    if previous_ms is None or timestamp_ms - previous_ms > gap_ms:
        current_cluster += 1
    return current_cluster, current_cluster


def detect_drum_event_streams(
    y: np.ndarray,
    sr: int,
    config: DrumDetectionConfig = DrumDetectionConfig(),
) -> dict[str, list[DrumEvent]]:
    y = np.asarray(y, dtype=np.float32).reshape(-1)
    if y.size == 0 or sr <= 0:
        return empty_drum_streams()
    _, perc = librosa.effects.hpss(y)
    hop = max(64, int(config.hop_length))
    n_fft = max(512, int(config.fft_size))
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
        peaks = librosa.util.peak_pick(_norm01(onset_env), pre_max=1, post_max=1, pre_avg=2, post_avg=2, delta=0.025, wait=1)
        frames = np.asarray(peaks, dtype=int)
    stft = np.abs(librosa.stft(perc, n_fft=n_fft, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    centroids = librosa.feature.spectral_centroid(S=stft, sr=sr)[0]
    bandwidths = librosa.feature.spectral_bandwidth(S=stft, sr=sr)[0]
    rms = librosa.feature.rms(y=perc, hop_length=hop)[0]
    rms01 = _norm01(rms)
    high_energy01 = _band_energy_curve(freqs, stft, 2500, min(sr / 2, 14000))
    onset01 = _norm01(onset_env)
    raw_events: list[DrumEvent] = []
    feature_cache: dict[int, dict[str, float]] = {}

    def features_at(frame: int) -> dict[str, float]:
        cached = feature_cache.get(frame)
        if cached is not None:
            return cached
        spectrum = stft[:, frame]
        total = float(np.sum(spectrum)) + 1e-9
        low = _band_energy(freqs, spectrum, 20, 160)
        mid_low = _band_energy(freqs, spectrum, 160, 700)
        mid = _band_energy(freqs, spectrum, 700, 2500)
        high = _band_energy(freqs, spectrum, 2500, min(sr / 2, 14000))
        centroid = float(centroids[frame]) if frame < len(centroids) else 0.0
        spread = float(bandwidths[frame]) if frame < len(bandwidths) else 0.0
        decay_energy = high_energy01 if high / total >= 0.30 else rms01
        decay = _decay_ratio(
            decay_energy,
            frame,
            sr=sr,
            hop_length=hop,
            early_ms=config.decay_early_ms,
            late_ms=config.decay_late_ms,
        )
        previous = float(onset01[frame - 1]) if frame > 0 and frame - 1 < len(onset01) else 0.0
        current = float(onset01[frame]) if frame < len(onset01) else 0.0
        features = {
            "low_ratio": low / total,
            "mid_low_ratio": mid_low / total,
            "mid_ratio": mid / total,
            "high_ratio": high / total,
            "kick_focus_ratio": _band_energy(freqs, spectrum, 30, 95) / total,
            "snare_body_ratio": _band_energy(freqs, spectrum, 150, 380) / total,
            "snare_crack_ratio": _band_energy(
                freqs,
                spectrum,
                2400,
                min(7200, sr / 2),
            )
            / total,
            "tom_focus_ratio": _band_energy(freqs, spectrum, 90, 230) / total,
            "hat_air_ratio": _band_energy(
                freqs,
                spectrum,
                min(6200, (sr / 2) * 0.6),
                max(100.0, (sr / 2) - 80.0),
            )
            / total,
            "cymbal_air_ratio": _band_energy(
                freqs,
                spectrum,
                2800,
                min(11000, max(100.0, (sr / 2) - 80.0)),
            )
            / total,
            "centroid_hz": centroid,
            "spectral_spread01": min(1.0, spread / max(1.0, sr / 2)),
            "transient_sharpness": min(1.0, max(0.0, current - previous)),
            "decay_profile": min(1.0, decay),
            "onset_strength": current,
            "analysis_hop_ms": (1000.0 * hop) / float(sr),
            "analysis_version": 2.0,
        }
        feature_cache[frame] = features
        return features

    def append_event(
        frame: int,
        drum_type: str,
        confidence: float,
        *,
        cluster_id: int | None,
        source: str,
        peak_strength: float = 0.0,
    ) -> None:
        features = features_at(frame)
        timestamp = float(librosa.frames_to_time(frame, sr=sr, hop_length=hop))
        current = float(features.get("onset_strength", 0.0))
        rms_value = float(rms01[frame]) if frame < len(rms01) else current
        velocity = max(
            0.08,
            min(1.0, (rms_value * 0.55) + (current * 0.25) + (peak_strength * 0.20)),
        )
        raw_events.append(
            DrumEvent(
                timestamp=round(timestamp, 4),
                velocity=round(velocity, 3),
                confidence=round(max(0.0, min(1.0, confidence)), 3),
                frequency_band_info={
                    key: round(float(value), 4)
                    for key, value in features.items()
                },
                cluster_id=cluster_id,
                drum_type=drum_type,
                source=source,
            )
        )

    previous_ms: int | None = None
    cluster = -1
    for frame in sorted(set(int(frame) for frame in frames if int(frame) < stft.shape[1])):
        features = features_at(frame)
        drum_type, confidence = classify_drum_hit(
            features,
            DrumClassifierThresholds(low_confidence_min=config.low_confidence_min),
        )
        timestamp = float(librosa.frames_to_time(frame, sr=sr, hop_length=hop))
        timestamp_ms = int(round(timestamp * 1000.0))
        cluster, cluster_id = _cluster_id(timestamp_ms, previous_ms, cluster, config.cluster_gap_ms)
        previous_ms = timestamp_ms
        peak_strength = float(features.get("onset_strength", 0.0))
        lane_confidence = _lane_confidence(drum_type, features, peak_strength)
        if drum_type == "drum_bus" or lane_confidence >= config.low_confidence_min:
            append_event(
                frame,
                drum_type,
                max(confidence, lane_confidence),
                cluster_id=cluster_id,
                source="drummer_x_hybrid",
                peak_strength=peak_strength,
            )
        if config.prefer_recall:
            for lane_type in ("kick", "snare", "tom", "hihat", "cymbal"):
                if lane_type == drum_type:
                    continue
                supplemental_confidence = _lane_confidence(
                    lane_type,
                    features,
                    peak_strength,
                )
                if supplemental_confidence < config.low_confidence_min:
                    continue
                append_event(
                    frame,
                    lane_type,
                    supplemental_confidence,
                    cluster_id=cluster_id,
                    source="drummer_x_multiband",
                    peak_strength=peak_strength,
                )

    if config.prefer_recall:
        candidates = _multiband_peak_candidates(stft, freqs, sr=sr, hop_length=hop)
        for drum_type, lane_peaks in candidates.items():
            for frame, peak_strength in lane_peaks:
                if frame >= stft.shape[1]:
                    continue
                confidence = _lane_confidence(
                    drum_type,
                    features_at(frame),
                    peak_strength,
                )
                if confidence < config.low_confidence_min:
                    continue
                append_event(
                    frame,
                    drum_type,
                    confidence,
                    cluster_id=frame,
                    source="drummer_x_multiband",
                    peak_strength=peak_strength,
                )
    streams = empty_drum_streams()
    compression_gap_ms = max(
        config.min_gap_ms,
        int(round((2500.0 * hop) / float(sr))),
    )
    for event in _compress_events(raw_events, compression_gap_ms):
        streams[stream_key_for_type(event.drum_type)].append(event)
    return streams


def detect_drum_event_streams_from_file(
    path: Path,
    config: DrumDetectionConfig = DrumDetectionConfig(),
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, list[DrumEvent]]:
    try:
        y, sr = librosa.load(str(path), sr=None, mono=True)
        streams = detect_drum_event_streams(np.asarray(y, dtype=np.float32), int(sr), config)
        if log_fn is not None:
            counts = {key: len(value) for key, value in streams.items()}
            log_fn(f"Drum intelligence: {counts}")
        return streams
    except Exception as exc:
        if log_fn is not None:
            log_fn(f"Drum intelligence skipped: {exc}")
        return empty_drum_streams()
