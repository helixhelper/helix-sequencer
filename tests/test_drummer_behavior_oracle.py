from __future__ import annotations

import numpy as np

from audio.drum_detection_oracle import (
    APPROVED_DRUMMER_BEHAVIOR_PROFILE,
    OracleDrumDetectionConfig,
    classify_drum_hit_oracle,
    detect_drum_event_streams_oracle,
)


def test_oracle_profile_is_pinned_to_approved_placeholder_lineage() -> None:
    assert APPROVED_DRUMMER_BEHAVIOR_PROFILE == "placeholder_v1_b27e8d7"


def test_oracle_preserves_single_label_family_rules() -> None:
    cases = [
        (
            {
                "low_ratio": 0.72,
                "mid_low_ratio": 0.12,
                "mid_ratio": 0.08,
                "high_ratio": 0.02,
                "centroid_hz": 120,
                "low_centroid_hz": 110,
                "spectral_spread01": 0.20,
                "transient_sharpness": 0.70,
                "decay_profile": 0.25,
            },
            "kick",
        ),
        (
            {
                "low_ratio": 0.02,
                "mid_low_ratio": 0.08,
                "mid_ratio": 0.18,
                "high_ratio": 0.72,
                "centroid_hz": 7000,
                "low_centroid_hz": 500,
                "spectral_spread01": 0.72,
                "transient_sharpness": 0.80,
                "decay_profile": 0.10,
            },
            "hihat",
        ),
        (
            {
                "low_ratio": 0.02,
                "mid_low_ratio": 0.06,
                "mid_ratio": 0.16,
                "high_ratio": 0.62,
                "centroid_hz": 6200,
                "low_centroid_hz": 500,
                "spectral_spread01": 0.72,
                "transient_sharpness": 0.22,
                "decay_profile": 0.72,
            },
            "cymbal",
        ),
        (
            {
                "low_ratio": 0.10,
                "mid_low_ratio": 0.18,
                "mid_ratio": 0.42,
                "high_ratio": 0.24,
                "centroid_hz": 1900,
                "low_centroid_hz": 500,
                "spectral_spread01": 0.52,
                "transient_sharpness": 0.55,
                "decay_profile": 0.22,
            },
            "snare",
        ),
        (
            {
                "low_ratio": 0.18,
                "mid_low_ratio": 0.46,
                "mid_ratio": 0.22,
                "high_ratio": 0.10,
                "centroid_hz": 850,
                "low_centroid_hz": 500,
                "spectral_spread01": 0.35,
                "transient_sharpness": 0.34,
                "decay_profile": 0.40,
            },
            "tom",
        ),
    ]
    for features, expected in cases:
        family, confidence = classify_drum_hit_oracle(features)
        assert family == expected
        assert confidence >= 0.34


def test_oracle_detector_emits_at_most_one_family_per_detected_onset() -> None:
    sr = 22050
    duration = 1.2
    y = np.zeros(int(sr * duration), dtype=np.float32)
    for start, frequency in ((0.20, 70.0), (0.55, 1800.0), (0.90, 6500.0)):
        index = int(start * sr)
        length = int(0.10 * sr)
        t = np.arange(length, dtype=np.float32) / sr
        burst = np.sin(2 * np.pi * frequency * t) * np.exp(-t * 35.0)
        y[index : index + length] += burst.astype(np.float32)

    streams = detect_drum_event_streams_oracle(
        y,
        sr,
        OracleDrumDetectionConfig(onset_delta=0.025, min_gap_ms=12),
        source_label="test:approved_placeholder_oracle",
    )
    events = [event for stream in streams.values() for event in stream]
    assert events
    timestamps = [event.timestamp_ms for event in events]
    assert len(timestamps) == len(set(timestamps))
    assert all("approved_placeholder_oracle" in event.source for event in events)
