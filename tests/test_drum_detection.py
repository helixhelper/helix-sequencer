from __future__ import annotations

import math
import unittest

import numpy as np

from audio.drum_classification import DrumEvent, classify_drum_hit
from audio.drum_detection import (
    DrumDetectionConfig,
    _compress_events,
    _decay_ratio,
    detect_drum_event_streams,
)


class DrumDetectionTests(unittest.TestCase):
    def test_same_lane_duplicates_compress_even_when_other_types_interleave(self) -> None:
        events = [
            DrumEvent(0.100, 0.5, 0.6, {}, 1, "hihat", "test"),
            DrumEvent(0.110, 0.8, 0.8, {}, 1, "kick", "test"),
            DrumEvent(0.120, 0.7, 0.9, {}, 1, "hihat", "test"),
        ]

        compressed = _compress_events(events, 24)

        hats = [event for event in compressed if event.drum_type == "hihat"]
        self.assertEqual(len(hats), 1)
        self.assertEqual(hats[0].timestamp, 0.120)

    def test_decay_ratio_distinguishes_short_and_sustained_high_frequency_hits(self) -> None:
        short = np.zeros(64, dtype=np.float32)
        short[5:8] = (1.0, 0.55, 0.18)
        sustained = np.zeros(64, dtype=np.float32)
        sustained[5:22] = np.linspace(1.0, 0.58, 17, dtype=np.float32)

        short_ratio = _decay_ratio(short, 4, sr=22050, hop_length=256)
        sustained_ratio = _decay_ratio(sustained, 4, sr=22050, hop_length=256)

        self.assertLess(short_ratio, 0.2)
        self.assertGreater(sustained_ratio, 0.5)

    def test_classifier_maps_frequency_profiles(self) -> None:
        kick, kick_conf = classify_drum_hit(
            {
                "low_ratio": 0.72,
                "mid_low_ratio": 0.12,
                "mid_ratio": 0.08,
                "high_ratio": 0.02,
                "centroid_hz": 120,
                "spectral_spread01": 0.2,
                "transient_sharpness": 0.7,
                "decay_profile": 0.25,
            }
        )
        hat, hat_conf = classify_drum_hit(
            {
                "low_ratio": 0.02,
                "mid_low_ratio": 0.08,
                "mid_ratio": 0.18,
                "high_ratio": 0.72,
                "centroid_hz": 7000,
                "spectral_spread01": 0.72,
                "transient_sharpness": 0.8,
                "decay_profile": 0.1,
            }
        )
        snare, snare_conf = classify_drum_hit(
            {
                "low_ratio": 0.10,
                "mid_low_ratio": 0.18,
                "mid_ratio": 0.42,
                "high_ratio": 0.24,
                "centroid_hz": 1900,
                "spectral_spread01": 0.52,
                "transient_sharpness": 0.55,
                "decay_profile": 0.22,
            }
        )
        tom, tom_conf = classify_drum_hit(
            {
                "low_ratio": 0.18,
                "mid_low_ratio": 0.46,
                "mid_ratio": 0.22,
                "high_ratio": 0.10,
                "centroid_hz": 850,
                "spectral_spread01": 0.35,
                "transient_sharpness": 0.34,
                "decay_profile": 0.40,
            }
        )
        cymbal, cymbal_conf = classify_drum_hit(
            {
                "low_ratio": 0.02,
                "mid_low_ratio": 0.06,
                "mid_ratio": 0.16,
                "high_ratio": 0.62,
                "centroid_hz": 6200,
                "spectral_spread01": 0.72,
                "transient_sharpness": 0.22,
                "decay_profile": 0.72,
            }
        )
        self.assertEqual(kick, "kick")
        self.assertEqual(hat, "hihat")
        self.assertEqual(snare, "snare")
        self.assertEqual(tom, "tom")
        self.assertEqual(cymbal, "cymbal")
        self.assertGreater(kick_conf, 0.4)
        self.assertGreater(hat_conf, 0.4)
        self.assertGreater(snare_conf, 0.4)
        self.assertGreater(tom_conf, 0.4)
        self.assertGreater(cymbal_conf, 0.4)

    def test_synthetic_percussive_signal_produces_events(self) -> None:
        sr = 22050
        y = np.zeros(sr, dtype=np.float32)
        for start, freq in ((0.20, 90), (0.50, 1800), (0.75, 6500)):
            idx = int(start * sr)
            length = int(0.08 * sr)
            t = np.arange(length) / sr
            burst = np.sin(2 * math.pi * freq * t) * np.exp(-t * 35)
            y[idx : idx + length] += burst.astype(np.float32)
        streams = detect_drum_event_streams(y, sr, DrumDetectionConfig(onset_delta=0.025, min_gap_ms=12))
        total = sum(len(events) for events in streams.values())
        self.assertGreaterEqual(total, 2)
        self.assertTrue(any(streams[key] for key in ("kick_events", "snare_events", "hihat_events", "drum_bus_events")))
        events = [event for stream in streams.values() for event in stream]
        self.assertTrue(
            {event.source for event in events}
            <= {"drummer_x_hybrid", "drummer_x_multiband"}
        )
        self.assertTrue(any(event.source == "drummer_x_multiband" for event in events))
        self.assertTrue(all(event.frequency_band_info["analysis_version"] == 2.0 for event in events))
        self.assertLess(min(abs(event.timestamp - 0.20) for event in events), 0.04)

    def test_short_and_sustained_noise_map_to_hat_and_cymbal(self) -> None:
        sr = 22050
        y = np.zeros(sr * 2, dtype=np.float32)
        rng = np.random.default_rng(414)
        for start, decay_seconds in ((0.20, 0.02), (1.00, 0.28)):
            length = int(0.50 * sr)
            t = np.arange(length) / sr
            burst = rng.normal(0.0, 1.0, length) * np.exp(-t / decay_seconds)
            offset = int(start * sr)
            y[offset : offset + length] += (burst * 0.7).astype(np.float32)

        streams = detect_drum_event_streams(
            y,
            sr,
            DrumDetectionConfig(onset_delta=0.025, min_gap_ms=12),
        )

        self.assertTrue(any(abs(event.timestamp - 0.20) < 0.04 for event in streams["hihat_events"]))
        self.assertTrue(any(abs(event.timestamp - 1.00) < 0.06 for event in streams["cymbal_events"]))

    def test_multiband_lanes_preserve_simultaneous_kick_and_hat(self) -> None:
        sr = 22050
        y = np.zeros(sr, dtype=np.float32)
        rng = np.random.default_rng(9)
        length = int(0.35 * sr)
        t = np.arange(length) / sr
        offset = int(0.30 * sr)
        kick = 0.8 * np.sin(2 * math.pi * 62 * t) * np.exp(-t / 0.13)
        hat = 0.35 * rng.normal(0.0, 1.0, length) * np.exp(-t / 0.018)
        y[offset : offset + length] = (kick + hat).astype(np.float32)

        streams = detect_drum_event_streams(
            y,
            sr,
            DrumDetectionConfig(onset_delta=0.025, min_gap_ms=12),
        )

        self.assertTrue(any(abs(event.timestamp - 0.30) < 0.04 for event in streams["kick_events"]))
        self.assertTrue(any(abs(event.timestamp - 0.30) < 0.04 for event in streams["hihat_events"]))


if __name__ == "__main__":
    unittest.main()
